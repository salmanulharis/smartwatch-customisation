package dev.openwear.s100.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.os.Build
import android.util.Log
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull

/**
 * One BLE connection to the watch: connect, MTU, notifications, bind, then a serial command API.
 * Android GATT allows one outstanding operation, so every operation goes through [gattOp].
 */
@SuppressLint("MissingPermission")   // callers check BLUETOOTH_CONNECT
class WatchLink(private val context: Context, val address: String) {
    enum class State { DISCONNECTED, CONNECTING, BINDING, READY }

    private val _state = MutableStateFlow(State.DISCONNECTED)
    val state: StateFlow<State> = _state
    val battery = MutableStateFlow(-1)
    val firmware = MutableStateFlow("")

    /** every notification from the watch (33f2 and 34f2) */
    val incoming = MutableSharedFlow<ByteArray>(extraBufferCapacity = 64, onBufferOverflow = BufferOverflow.DROP_OLDEST)

    private var gatt: BluetoothGatt? = null
    private var pending: CompletableDeferred<Int>? = null
    private val opLock = Mutex()
    private val cmdLock = Mutex()        // one protocol exchange at a time (write + expected reply)
    private var connected = CompletableDeferred<Boolean>()
    var maxLen = 20
        private set

    private val callback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            Log.i(TAG, "connection state $newState status $status")
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                connected.complete(true)
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                _state.value = State.DISCONNECTED
                connected.complete(false)
                pending?.complete(-1)
            }
        }
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) { pending?.complete(status) }
        override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) { pending?.complete(status) }
        override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) { pending?.complete(status) }
        override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) { pending?.complete(status) }

        @Deprecated("pre-33 callback")
        override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
            @Suppress("DEPRECATION") lastRead = c.value ?: ByteArray(0); pending?.complete(status)
        }
        override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray, status: Int) {
            lastRead = value; pending?.complete(status)
        }

        @Deprecated("pre-33 callback")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            @Suppress("DEPRECATION") handleNotify(c, c.value ?: return)
        }
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray) {
            handleNotify(c, value)
        }
    }
    private var lastRead = ByteArray(0)

    private fun handleNotify(c: BluetoothGattCharacteristic, value: ByteArray) {
        if (c.uuid == Protocol.BATTERY_LEVEL) { battery.value = value.firstOrNull()?.toInt() ?: -1; return }
        incoming.tryEmit(value.copyOf())
    }

    private suspend fun gattOp(timeoutMs: Long = 5000, start: (BluetoothGatt) -> Boolean): Int = opLock.withLock {
        val g = gatt ?: return -1
        val d = CompletableDeferred<Int>()
        pending = d
        if (!start(g)) { pending = null; return -2 }
        val r = withTimeoutOrNull(timeoutMs) { d.await() } ?: -3
        pending = null
        r
    }

    /** Connect, discover, subscribe and bind. Returns true when the watch accepted the bind. */
    suspend fun connect(): Boolean {
        close()
        _state.value = State.CONNECTING
        val dev: BluetoothDevice = context.getSystemService(BluetoothManager::class.java).adapter.getRemoteDevice(address)
        connected = CompletableDeferred()
        gatt = dev.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
        if (withTimeoutOrNull(20_000) { connected.await() } != true) { close(); return false }
        delay(300)
        if (gattOp(10_000) { it.discoverServices() } != BluetoothGatt.GATT_SUCCESS) { close(); return false }
        gattOp { it.requestMtu(247) }
        for (uuid in listOf(Protocol.CMD_NOTIFY to Protocol.CMD_SERVICE, Protocol.BIG_NOTIFY to Protocol.BIG_SERVICE,
                            Protocol.BATTERY_LEVEL to Protocol.BATTERY_SERVICE)) {
            if (!subscribe(uuid.second, uuid.first) && uuid.first != Protocol.BATTERY_LEVEL) { close(); return false }
        }
        read(Protocol.BIG_SERVICE, Protocol.BIG_CHAR)?.let { if (it.size >= 2) maxLen = ((it[0].toInt() and 0xFF) shl 8) or (it[1].toInt() and 0xFF) }
        read(Protocol.BATTERY_SERVICE, Protocol.BATTERY_LEVEL)?.firstOrNull()?.let { battery.value = it.toInt() and 0xFF }
        _state.value = State.BINDING
        val reply = request(Protocol.bind(), byteArrayOf(0x33, 0x04), 25_000)
        if (reply == null || reply.size < 3 || reply[2].toInt() != 1) { Log.w(TAG, "bind reply ${reply?.hex()}"); close(); return false }
        _state.value = State.READY
        request(Protocol.version(), byteArrayOf(0xA1.toByte()))?.let { firmware.value = String(it, 1, it.size - 1, Charsets.US_ASCII) }
        return true
    }

    fun close() {
        gatt?.let { it.disconnect(); it.close() }
        gatt = null
        _state.value = State.DISCONNECTED
    }

    private fun ch(service: java.util.UUID, uuid: java.util.UUID) = gatt?.getService(service)?.getCharacteristic(uuid)

    private suspend fun subscribe(service: java.util.UUID, uuid: java.util.UUID): Boolean {
        val c = ch(service, uuid) ?: return false
        val g = gatt ?: return false
        g.setCharacteristicNotification(c, true)
        val d = c.getDescriptor(Protocol.CCCD) ?: return false
        return gattOp {
            if (Build.VERSION.SDK_INT >= 33) it.writeDescriptor(d, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) == 0
            else { @Suppress("DEPRECATION") run { d.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE; it.writeDescriptor(d) } }
        } == BluetoothGatt.GATT_SUCCESS
    }

    private suspend fun read(service: java.util.UUID, uuid: java.util.UUID): ByteArray? {
        val c = ch(service, uuid) ?: return null
        return if (gattOp { it.readCharacteristic(c) } == BluetoothGatt.GATT_SUCCESS) lastRead else null
    }

    /** Write to 33f1 (with response) or 34f1 ("big", write without response). */
    suspend fun write(data: ByteArray, big: Boolean = false): Boolean {
        val c = if (big) ch(Protocol.BIG_SERVICE, Protocol.BIG_CHAR) else ch(Protocol.CMD_SERVICE, Protocol.CMD_CHAR)
        c ?: return false
        val type = if (big) BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE else BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        return gattOp {
            if (Build.VERSION.SDK_INT >= 33) it.writeCharacteristic(c, data, type) == 0
            else { @Suppress("DEPRECATION") run { c.writeType = type; c.value = data; it.writeCharacteristic(c) } }
        } == BluetoothGatt.GATT_SUCCESS
    }

    /** Wait for the next notification starting with [prefix]. */
    suspend fun expect(prefix: ByteArray, timeoutMs: Long = 5000): ByteArray? = withTimeoutOrNull(timeoutMs) {
        incoming.first { it.size >= prefix.size && prefix.indices.all { i -> it[i] == prefix[i] } }
    }

    /** Write and wait for the reply, as one exchange (subscribe before writing so no reply is missed). */
    suspend fun request(data: ByteArray, prefix: ByteArray, timeoutMs: Long = 5000, big: Boolean = false): ByteArray? =
        cmdLock.withLock { exchange(data, prefix, timeoutMs, big) }

    /** Run several exchanges without other commands interleaving (notification chunks, dial upload). */
    suspend fun <T> session(block: suspend Session.() -> T): T = cmdLock.withLock { Session().block() }

    inner class Session {
        suspend fun request(data: ByteArray, prefix: ByteArray, timeoutMs: Long = 5000, big: Boolean = false) =
            exchange(data, prefix, timeoutMs, big)
        suspend fun write(data: ByteArray, big: Boolean = false) = this@WatchLink.write(data, big)
        suspend fun expect(prefix: ByteArray, timeoutMs: Long = 5000) = this@WatchLink.expect(prefix, timeoutMs)
    }

    private suspend fun exchange(data: ByteArray, prefix: ByteArray, timeoutMs: Long, big: Boolean): ByteArray? =
        coroutineScope {
            // start listening before writing, so a fast reply is not missed
            val reply = async(start = CoroutineStart.UNDISPATCHED) { expect(prefix, timeoutMs) }
            if (!write(data, big)) { reply.cancel(); null } else reply.await()
        }

    companion object {
        const val TAG = "WatchLink"
        fun ByteArray.hex() = joinToString(" ") { "%02x".format(it) }
    }
}
