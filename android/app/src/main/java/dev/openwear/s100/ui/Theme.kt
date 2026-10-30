package dev.openwear.s100.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** CMF-style: true black, off-white, greys, one orange accent (same tokens as the watch UI). */
object C {
    val Black = Color(0xFF000000)
    val Card = Color(0xFF161616)
    val Line = Color(0xFF2A2A2A)
    val Text = Color(0xFFF5F5F5)
    val Dim = Color(0xFF8C8C8C)
    val Orange = Color(0xFFFF5A1E)
}

@Composable
fun S100Theme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = C.Orange, onPrimary = C.Black, background = C.Black, surface = C.Card,
            onBackground = C.Text, onSurface = C.Text, secondary = C.Dim, surfaceVariant = C.Card,
        ),
        content = content,
    )
}

val Mono = FontFamily.Monospace
val Big = TextStyle(fontSize = 44.sp, fontWeight = FontWeight.Light, color = C.Text, letterSpacing = (-1).sp)
val Label = TextStyle(fontSize = 12.sp, color = C.Dim, fontFamily = Mono, letterSpacing = 1.5.sp)

@Composable
fun Card(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(C.Card).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp), content = content,
    )
}

@Composable
fun SectionLabel(text: String) = Text(text.uppercase(), style = Label, modifier = Modifier.padding(start = 6.dp, top = 18.dp, bottom = 8.dp))

@Composable
fun ToggleRow(title: String, sub: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = C.Text, fontSize = 16.sp)
            if (sub.isNotEmpty()) Text(sub, color = C.Dim, fontSize = 13.sp)
        }
        Spacer(Modifier.width(12.dp))
        Switch(checked, onChange, colors = SwitchDefaults.colors(
            checkedThumbColor = C.Black, checkedTrackColor = C.Orange,
            uncheckedThumbColor = C.Dim, uncheckedTrackColor = C.Line, uncheckedBorderColor = C.Line))
    }
}
