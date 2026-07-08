use anyhow::{Context, Result};
use serde_yaml::Value;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

pub type ConfigMap = HashMap<String, Value>;

pub fn load_yaml(path: &Path) -> Result<ConfigMap> {
    let content = fs::read_to_string(path)
        .with_context(|| format!("Failed to read config file: {}", path.display()))?;
    let data: Value = serde_yaml::from_str(&content)
        .with_context(|| format!("Failed to parse YAML: {}", path.display()))?;
    match data {
        Value::Mapping(map) => {
            let mut result = HashMap::new();
            for (k, v) in map {
                if let Value::String(key) = k {
                    result.insert(key, v);
                }
            }
            Ok(result)
        }
        _ => anyhow::bail!("Config file must contain a mapping: {}", path.display()),
    }
}

pub fn load_runtime_config(config_path: &Path) -> Result<ConfigMap> {
    load_yaml(config_path)
}

pub fn load_label_dict(config_path: &Path) -> Result<ConfigMap> {
    load_yaml(config_path)
}

#[allow(dead_code)]
pub fn get_f64(config: &ConfigMap, key: &str, default: f64) -> f64 {
    config
        .get(key)
        .and_then(|v| match v {
            Value::Number(n) => n.as_f64(),
            _ => None,
        })
        .unwrap_or(default)
}

pub fn get_bool(config: &ConfigMap, key: &str, default: bool) -> bool {
    config
        .get(key)
        .and_then(|v| match v {
            Value::Bool(b) => Some(*b),
            _ => None,
        })
        .unwrap_or(default)
}

#[allow(dead_code)]
pub fn get_string(config: &ConfigMap, key: &str, default: &str) -> String {
    config
        .get(key)
        .and_then(|v| match v {
            Value::String(s) => Some(s.clone()),
            _ => None,
        })
        .unwrap_or_else(|| default.to_string())
}

#[allow(dead_code)]
pub fn get_string_list(config: &ConfigMap, key: &str) -> Vec<String> {
    config
        .get(key)
        .and_then(|v| match v {
            Value::Sequence(seq) => Some(
                seq.iter()
                    .filter_map(|item| match item {
                        Value::String(s) => Some(s.clone()),
                        _ => None,
                    })
                    .collect(),
            ),
            _ => None,
        })
        .unwrap_or_default()
}
