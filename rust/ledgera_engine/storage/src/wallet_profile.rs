pub const WALLET_ICON_KEYS: [&str; 6] = [
    "wallet",
    "cash",
    "card",
    "bank",
    "savings",
    "investment",
];

pub fn is_valid_wallet_icon(value: &str) -> bool {
    WALLET_ICON_KEYS.contains(&value)
}
