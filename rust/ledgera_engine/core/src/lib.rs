pub const MONEY_SCALE: u32 = 2;
pub const RATE_SCALE: u32 = 6;

pub type CoreResult<T> = Result<T, String>;

fn pow10(power: u32) -> CoreResult<i128> {
    10_i128
        .checked_pow(power)
        .ok_or_else(|| "numeric scale overflow".to_owned())
}

fn parse_scaled_decimal(text: &str, scale: u32) -> CoreResult<i128> {
    let trimmed = text.trim();
    let normalized = if trimmed.is_empty() { "0" } else { trimmed };

    let (sign, unsigned) = if let Some(rest) = normalized.strip_prefix('-') {
        (-1_i128, rest)
    } else if let Some(rest) = normalized.strip_prefix('+') {
        (1_i128, rest)
    } else {
        (1_i128, normalized)
    };

    let mut parts = unsigned.split('.');
    let int_part = parts.next().unwrap_or_default();
    let frac_part = parts.next().unwrap_or_default();

    if parts.next().is_some() {
        return Err("invalid decimal value".to_owned());
    }

    if !int_part.chars().all(|ch| ch.is_ascii_digit())
        || !frac_part.chars().all(|ch| ch.is_ascii_digit())
    {
        return Err("invalid decimal value".to_owned());
    }

    let int_value = if int_part.is_empty() {
        0_i128
    } else {
        int_part
            .parse::<i128>()
            .map_err(|_| "invalid decimal value".to_owned())?
    };
    let frac_value = if frac_part.is_empty() {
        0_i128
    } else {
        frac_part
            .parse::<i128>()
            .map_err(|_| "invalid decimal value".to_owned())?
    };

    let frac_len = frac_part.len() as u32;
    let base = int_value
        .checked_mul(pow10(frac_len)?)
        .and_then(|value| value.checked_add(frac_value))
        .ok_or_else(|| "decimal value too large".to_owned())?;

    let quantized_abs = if frac_len <= scale {
        base.checked_mul(pow10(scale - frac_len)?)
            .ok_or_else(|| "decimal value too large".to_owned())?
    } else {
        let divisor = pow10(frac_len - scale)?;
        let quotient = base / divisor;
        let remainder = base % divisor;
        let should_round_up = remainder.checked_mul(2).unwrap_or(i128::MAX) >= divisor;
        if should_round_up {
            quotient
                .checked_add(1)
                .ok_or_else(|| "decimal value too large".to_owned())?
        } else {
            quotient
        }
    };

    quantized_abs
        .checked_mul(sign)
        .ok_or_else(|| "decimal value too large".to_owned())
}

fn scaled_to_float(value: i128, scale: u32) -> CoreResult<f64> {
    let divisor = pow10(scale)? as f64;
    Ok(value as f64 / divisor)
}

fn scaled_to_text(value: i128, scale: u32) -> CoreResult<String> {
    let sign = if value < 0 { "-" } else { "" };
    let abs_value = value.abs();
    let divisor = pow10(scale)?;
    let integer = abs_value / divisor;
    if scale == 0 {
        return Ok(format!("{sign}{integer}"));
    }
    let fraction = abs_value % divisor;
    Ok(format!(
        "{sign}{integer}.{fraction:0width$}",
        width = scale as usize
    ))
}

fn round_div_half_up(numerator: i128, denominator: i128) -> CoreResult<i128> {
    if denominator == 0 {
        return Err("division by zero".to_owned());
    }

    let sign = if (numerator < 0) ^ (denominator < 0) {
        -1_i128
    } else {
        1_i128
    };
    let abs_numerator = numerator.abs();
    let abs_denominator = denominator.abs();
    let quotient = abs_numerator / abs_denominator;
    let remainder = abs_numerator % abs_denominator;
    let rounded = if remainder.checked_mul(2).unwrap_or(i128::MAX) >= abs_denominator {
        quotient
            .checked_add(1)
            .ok_or_else(|| "numeric value too large".to_owned())?
    } else {
        quotient
    };

    rounded
        .checked_mul(sign)
        .ok_or_else(|| "numeric value too large".to_owned())
}

pub fn convert_amount(amount: f64, rate: f64) -> f64 {
    amount * rate
}

pub fn calculate_daily_burn(total_spent: f64, days_passed: i32) -> f64 {
    if days_passed <= 0 {
        total_spent
    } else {
        total_spent / days_passed as f64
    }
}

pub fn quantize_money_text(value: &str) -> CoreResult<String> {
    scaled_to_text(parse_scaled_decimal(value, MONEY_SCALE)?, MONEY_SCALE)
}

pub fn quantize_rate_text(value: &str) -> CoreResult<String> {
    scaled_to_text(parse_scaled_decimal(value, RATE_SCALE)?, RATE_SCALE)
}

pub fn to_money_float(value: &str) -> CoreResult<f64> {
    scaled_to_float(parse_scaled_decimal(value, MONEY_SCALE)?, MONEY_SCALE)
}

pub fn to_rate_float(value: &str) -> CoreResult<f64> {
    scaled_to_float(parse_scaled_decimal(value, RATE_SCALE)?, RATE_SCALE)
}

pub fn to_minor_units(value: &str) -> CoreResult<i64> {
    let scaled = parse_scaled_decimal(value, MONEY_SCALE)?;
    i64::try_from(scaled).map_err(|_| "minor units overflow".to_owned())
}

pub fn minor_to_money(value: &str) -> CoreResult<f64> {
    let units = parse_scaled_decimal(value, 0)?;
    scaled_to_float(units, MONEY_SCALE)
}

pub fn minor_to_money_value(value: i64) -> f64 {
    value as f64 / 100.0
}

pub fn build_rate(amount_original: &str, amount_base: &str, currency: &str) -> CoreResult<f64> {
    if currency.trim().eq_ignore_ascii_case("KZT") {
        return Ok(1.0);
    }

    let amount_original_scaled = parse_scaled_decimal(amount_original, MONEY_SCALE)?;
    if amount_original_scaled == 0 {
        return Ok(1.0);
    }

    let amount_base_scaled = parse_scaled_decimal(amount_base, MONEY_SCALE)?;
    let numerator = amount_base_scaled
        .checked_mul(pow10(RATE_SCALE)?)
        .ok_or_else(|| "rate overflow".to_owned())?;
    let rate_scaled = round_div_half_up(numerator, amount_original_scaled)?;
    scaled_to_float(rate_scaled, RATE_SCALE)
}

pub fn money_abs(value: &str) -> CoreResult<f64> {
    let scaled = parse_scaled_decimal(value, MONEY_SCALE)?;
    scaled_to_float(scaled.abs(), MONEY_SCALE)
}

pub fn rate_to_text(value: &str) -> CoreResult<String> {
    quantize_rate_text(value)
}

pub fn money_diff_text(left: &str, right: &str) -> CoreResult<String> {
    let left_scaled = parse_scaled_decimal(left, MONEY_SCALE)?;
    let right_scaled = parse_scaled_decimal(right, MONEY_SCALE)?;
    scaled_to_text(
        left_scaled
            .checked_sub(right_scaled)
            .ok_or_else(|| "money difference overflow".to_owned())?,
        MONEY_SCALE,
    )
}

pub fn rate_diff_text(left: &str, right: &str) -> CoreResult<String> {
    let left_scaled = parse_scaled_decimal(left, RATE_SCALE)?;
    let right_scaled = parse_scaled_decimal(right, RATE_SCALE)?;
    scaled_to_text(
        left_scaled
            .checked_sub(right_scaled)
            .ok_or_else(|| "rate difference overflow".to_owned())?,
        RATE_SCALE,
    )
}

pub fn rate_float_from_text(value: &str) -> CoreResult<f64> {
    scaled_to_float(parse_scaled_decimal(value, RATE_SCALE)?, RATE_SCALE)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn money_rounding_half_up() {
        assert_eq!(to_money_float("1.005").unwrap(), 1.01);
        assert_eq!(to_money_float("-1.005").unwrap(), -1.01);
    }

    #[test]
    fn rate_rounding_half_up() {
        assert_eq!(to_rate_float("1.2345675").unwrap(), 1.234568);
    }

    #[test]
    fn minor_units_round_trip() {
        assert_eq!(to_minor_units("123.455").unwrap(), 12346);
        assert_eq!(minor_to_money("12346").unwrap(), 123.46);
    }

    #[test]
    fn build_rate_preserves_special_cases() {
        assert_eq!(build_rate("10.00", "5000.00", "USD").unwrap(), 500.0);
        assert_eq!(build_rate("0", "5000.00", "USD").unwrap(), 1.0);
        assert_eq!(build_rate("10.00", "5000.00", "KZT").unwrap(), 1.0);
    }

    #[test]
    fn text_helpers_preserve_scale_and_sign() {
        assert_eq!(quantize_money_text("1.005").unwrap(), "1.01");
        assert_eq!(quantize_money_text("-1.005").unwrap(), "-1.01");
        assert_eq!(quantize_rate_text("1.2345675").unwrap(), "1.234568");
        assert_eq!(rate_to_text("1.2").unwrap(), "1.200000");
        assert_eq!(money_diff_text("10.005", "1.00").unwrap(), "9.01");
        assert_eq!(rate_diff_text("1.2345675", "0.2345674").unwrap(), "1.000001");
    }
}
