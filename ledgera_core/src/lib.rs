use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const MONEY_SCALE: u32 = 2;
const RATE_SCALE: u32 = 6;
fn pow10(power: u32) -> PyResult<i128> {
    10_i128
        .checked_pow(power)
        .ok_or_else(|| PyValueError::new_err("numeric scale overflow"))
}

fn py_value_to_text(value: &Bound<'_, PyAny>, default: &str) -> PyResult<String> {
    if value.is_none() {
        return Ok(default.to_owned());
    }
    Ok(value.str()?.to_str()?.trim().to_owned())
}

fn parse_scaled_decimal(text: &str, scale: u32) -> PyResult<i128> {
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
        return Err(PyValueError::new_err("invalid decimal value"));
    }

    if !int_part.chars().all(|ch| ch.is_ascii_digit())
        || !frac_part.chars().all(|ch| ch.is_ascii_digit())
    {
        return Err(PyValueError::new_err("invalid decimal value"));
    }

    let int_value = if int_part.is_empty() {
        0_i128
    } else {
        int_part
            .parse::<i128>()
            .map_err(|_| PyValueError::new_err("invalid decimal value"))?
    };
    let frac_value = if frac_part.is_empty() {
        0_i128
    } else {
        frac_part
            .parse::<i128>()
            .map_err(|_| PyValueError::new_err("invalid decimal value"))?
    };

    let frac_len = frac_part.len() as u32;
    let base = int_value
        .checked_mul(pow10(frac_len)?)
        .and_then(|value| value.checked_add(frac_value))
        .ok_or_else(|| PyValueError::new_err("decimal value too large"))?;

    let quantized_abs = if frac_len <= scale {
        base.checked_mul(pow10(scale - frac_len)?)
            .ok_or_else(|| PyValueError::new_err("decimal value too large"))?
    } else {
        let divisor = pow10(frac_len - scale)?;
        let quotient = base / divisor;
        let remainder = base % divisor;
        let should_round_up = remainder.checked_mul(2).unwrap_or(i128::MAX) >= divisor;
        if should_round_up {
            quotient
                .checked_add(1)
                .ok_or_else(|| PyValueError::new_err("decimal value too large"))?
        } else {
            quotient
        }
    };

    quantized_abs
        .checked_mul(sign)
        .ok_or_else(|| PyValueError::new_err("decimal value too large"))
}

fn scaled_to_float(value: i128, scale: u32) -> PyResult<f64> {
    let divisor = pow10(scale)? as f64;
    Ok(value as f64 / divisor)
}

fn round_div_half_up(numerator: i128, denominator: i128) -> PyResult<i128> {
    if denominator == 0 {
        return Err(PyValueError::new_err("division by zero"));
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
            .ok_or_else(|| PyValueError::new_err("numeric value too large"))?
    } else {
        quotient
    };

    rounded
        .checked_mul(sign)
        .ok_or_else(|| PyValueError::new_err("numeric value too large"))
}

#[pyfunction]
fn convert_amount(amount: f64, rate: f64) -> PyResult<f64> {
    Ok(amount * rate)
}

#[pyfunction]
fn calculate_daily_burn(total_spent: f64, days_passed: i32) -> PyResult<f64> {
    if days_passed <= 0 {
        return Ok(total_spent);
    }
    Ok(total_spent / days_passed as f64)
}

#[pyfunction]
fn to_money_float(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let scaled = parse_scaled_decimal(&py_value_to_text(value, "0")?, MONEY_SCALE)?;
    scaled_to_float(scaled, MONEY_SCALE)
}

#[pyfunction]
fn to_rate_float(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let scaled = parse_scaled_decimal(&py_value_to_text(value, "0")?, RATE_SCALE)?;
    scaled_to_float(scaled, RATE_SCALE)
}

#[pyfunction]
fn to_minor_units(value: &Bound<'_, PyAny>) -> PyResult<i64> {
    let scaled = parse_scaled_decimal(&py_value_to_text(value, "0")?, MONEY_SCALE)?;
    i64::try_from(scaled).map_err(|_| PyValueError::new_err("minor units overflow"))
}

#[pyfunction]
fn minor_to_money(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let units = parse_scaled_decimal(&py_value_to_text(value, "0")?, 0)?;
    scaled_to_float(units, MONEY_SCALE)
}

#[pyfunction]
fn build_rate(
    amount_original: &Bound<'_, PyAny>,
    amount_base: &Bound<'_, PyAny>,
    currency: &str,
) -> PyResult<f64> {
    if currency.trim().eq_ignore_ascii_case("KZT") {
        return Ok(1.0);
    }

    let amount_original_scaled =
        parse_scaled_decimal(&py_value_to_text(amount_original, "0")?, MONEY_SCALE)?;
    if amount_original_scaled == 0 {
        return Ok(1.0);
    }

    let amount_base_scaled =
        parse_scaled_decimal(&py_value_to_text(amount_base, "0")?, MONEY_SCALE)?;
    let numerator = amount_base_scaled
        .checked_mul(pow10(RATE_SCALE)?)
        .ok_or_else(|| PyValueError::new_err("rate overflow"))?;
    let rate_scaled = round_div_half_up(numerator, amount_original_scaled)?;
    scaled_to_float(rate_scaled, RATE_SCALE)
}

#[pyfunction]
fn money_abs(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let scaled = parse_scaled_decimal(&py_value_to_text(value, "0")?, MONEY_SCALE)?;
    scaled_to_float(scaled.abs(), MONEY_SCALE)
}

#[pymodule]
fn ledgera_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(convert_amount, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_daily_burn, m)?)?;
    m.add_function(wrap_pyfunction!(to_money_float, m)?)?;
    m.add_function(wrap_pyfunction!(to_rate_float, m)?)?;
    m.add_function(wrap_pyfunction!(to_minor_units, m)?)?;
    m.add_function(wrap_pyfunction!(minor_to_money, m)?)?;
    m.add_function(wrap_pyfunction!(build_rate, m)?)?;
    m.add_function(wrap_pyfunction!(money_abs, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::types::PyString;
    use pyo3::Python;

    #[test]
    fn test_convert_amount() {
        assert_eq!(convert_amount(100.0, 2.0).unwrap(), 200.0);
    }

    #[test]
    fn test_calculate_daily_burn() {
        assert_eq!(calculate_daily_burn(100.0, 4).unwrap(), 25.0);
        assert_eq!(calculate_daily_burn(100.0, 0).unwrap(), 100.0);
    }

    #[test]
    fn test_money_rounding_half_up() {
        Python::initialize();
        Python::attach(|py| {
            let value = PyString::new(py, "1.005");
            assert_eq!(to_money_float(&value.into_any()).unwrap(), 1.01);
            let negative = PyString::new(py, "-1.005");
            assert_eq!(to_money_float(&negative.into_any()).unwrap(), -1.01);
        });
    }

    #[test]
    fn test_rate_rounding_half_up() {
        Python::initialize();
        Python::attach(|py| {
            let value = PyString::new(py, "1.2345675");
            assert_eq!(to_rate_float(&value.into_any()).unwrap(), 1.234568);
        });
    }

    #[test]
    fn test_minor_units_round_trip() {
        Python::initialize();
        Python::attach(|py| {
            let value = PyString::new(py, "123.455");
            assert_eq!(to_minor_units(&value.into_any()).unwrap(), 12346);
            let units = PyString::new(py, "12346");
            assert_eq!(minor_to_money(&units.into_any()).unwrap(), 123.46);
        });
    }

    #[test]
    fn test_build_rate_preserves_special_cases() {
        Python::initialize();
        Python::attach(|py| {
            let amount_original = PyString::new(py, "10.00");
            let amount_base = PyString::new(py, "5000.00");
            assert_eq!(
                build_rate(
                    &amount_original.clone().into_any(),
                    &amount_base.clone().into_any(),
                    "USD",
                )
                .unwrap(),
                500.0
            );

            let zero_original = PyString::new(py, "0");
            assert_eq!(
                build_rate(&zero_original.into_any(), &amount_base.clone().into_any(), "USD")
                    .unwrap(),
                1.0
            );

            assert_eq!(
                build_rate(&amount_original.into_any(), &amount_base.into_any(), "KZT").unwrap(),
                1.0
            );
        });
    }

    #[test]
    fn test_money_abs_quantizes_before_abs() {
        Python::initialize();
        Python::attach(|py| {
            let value = PyString::new(py, "-10.004");
            assert_eq!(money_abs(&value.into_any()).unwrap(), 10.0);
        });
    }
}
