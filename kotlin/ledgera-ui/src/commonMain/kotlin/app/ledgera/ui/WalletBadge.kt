package app.ledgera.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.Image
import app.ledgera.model.WalletOption
import app.ledgera.model.WalletSettingsItem
import app.ledgera.resources.Res
import app.ledgera.resources.ic_wallet
import app.ledgera.resources.ic_wallet_bank
import app.ledgera.resources.ic_wallet_card
import app.ledgera.resources.ic_wallet_cash
import app.ledgera.resources.ic_wallet_investment
import app.ledgera.resources.ic_wallet_savings
import org.jetbrains.compose.resources.painterResource

internal val WalletIconKeys = listOf("wallet", "cash", "card", "bank", "savings", "investment")

@Composable
internal fun WalletBadge(
    name: String,
    color: String,
    iconKey: String,
    size: Dp = 30.dp,
) {
    val badgeColor = color.toComposeTagColor() ?: MaterialTheme.colorScheme.primary
    Box(
        Modifier
            .size(size)
            .clip(CircleShape)
            .background(badgeColor)
            .semantics { contentDescription = name },
        contentAlignment = Alignment.Center,
    ) {
        Image(
            painter = walletIconPainter(iconKey),
            contentDescription = null,
            modifier = Modifier.size(size * 0.58f),
            colorFilter = androidx.compose.ui.graphics.ColorFilter.tint(Color.White),
        )
    }
}

@Composable
private fun walletIconPainter(iconKey: String): Painter = when (iconKey) {
    "cash" -> painterResource(Res.drawable.ic_wallet_cash)
    "card" -> painterResource(Res.drawable.ic_wallet_card)
    "bank" -> painterResource(Res.drawable.ic_wallet_bank)
    "savings" -> painterResource(Res.drawable.ic_wallet_savings)
    "investment" -> painterResource(Res.drawable.ic_wallet_investment)
    else -> painterResource(Res.drawable.ic_wallet)
}

@Composable
internal fun WalletBadge(wallet: WalletOption, size: Dp = 30.dp) {
    WalletBadge(wallet.name, wallet.color, wallet.iconKey, size)
}

@Composable
internal fun WalletBadge(wallet: WalletSettingsItem, size: Dp = 30.dp) {
    WalletBadge(wallet.name, wallet.color, wallet.iconKey, size)
}
