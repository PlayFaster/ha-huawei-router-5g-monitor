# Signal Metric Guard Bands: Huawei Router 5G

To ensure the Home Assistant UI remains clean and professional, we apply "Guard Bands" to incoming router data. If a value falls outside these realistic physical limits, the sensor is marked as `Unavailable` to prevent misleading spikes or "ghost" zeros from polluting your long-term statistics.

## Guard Band Strategy

We use a **Declarative Validation** approach. Limits are defined directly within the `HuaweiSensorEntityDescription` for each sensor. The base sensor class automatically enforces these bounds before passing the value to Home Assistant.

### Why this approach?

- **Readability**: Limits are visible next to the sensor definition.
- **Maintainability**: Changing a limit requires updating only one number, not complex logic.
- **Data Integrity**: Prevents impossible values (e.g., +100dBm signal) from being recorded in the database.
- **UI Stability**: Ensures that dashboards and graphs remain readable and aren't skewed by transient API artifacts or hardware glitches.

---

## Validated Signal Limits

| Metric Category | Metric Name               | Min  | Max             | Action if Out of Bounds |
| :-------------- | :------------------------ | :--- | :-------------- | :---------------------- |
| **LTE Signal**  | RSRP                      | -150 | -30             | Set to `Unavailable`    |
|                 | RSRQ                      | -50  | 0               | Set to `Unavailable`    |
|                 | RSSI                      | -120 | -20             | Set to `Unavailable`    |
|                 | SINR                      | -30  | 50              | Set to `Unavailable`    |
|                 | Transmit Power            | -30  | 40              | Set to `Unavailable`    |
| **5G Signal**   | RSRP                      | -150 | -30             | Set to `Unavailable`    |
|                 | RSRQ                      | -50  | 0               | Set to `Unavailable`    |
|                 | SINR                      | -30  | 50              | Set to `Unavailable`    |
|                 | Transmit Power            | -30  | 40              | Set to `Unavailable`    |
| **Diagnostics** | Signal Bars               | 0    | 5               | Set to `Unavailable`    |
|                 | Battery                   | 0    | 100             | Set to `Unavailable`    |
|                 | WiFi Users                | 0    | 255             | Set to `Unavailable`    |
|                 | Uptime / Connection Time  | 0    | None            | Set to `Unavailable`    |
| **Data Usage**  | Total / Monthly / Day Use | 0    | 100TB           | Set to `Unavailable`    |
| **Data Rates**  | Download / Upload Rates   | 0    | 1.25GB/s (10Gb) | Set to `Unavailable`    |
| **SMS**         | All Message Counts        | 0    | 10000           | Set to `Unavailable`    |

---

## Implementation Details

The `HuaweiSensorEntityDescription` dataclass includes optional `min_limit` and `max_limit` attributes.

**Example Definition:**

```python
HuaweiSensorEntityDescription(
    key="rsrp",
    name="LTE RSRP",
    ...
    min_limit=-150,
    max_limit=-30,
    value_fn=lambda data: _safe_float(_get_signal_value(data, "rsrp")),
)
```

The `native_value` property in the sensor class performs the following check:

```python
val = self.entity_description.value_fn(self.coordinator.data)
min_limit = self.entity_description.min_limit
max_limit = self.entity_description.max_limit

if val is not None and (min_limit is not None or max_limit is not None):
    try:
        num_val = float(val)
        if min_limit is not None and num_val < min_limit:
            return None
        if max_limit is not None and num_val > max_limit:
            return None
    except (ValueError, TypeError):
        pass
return val
```

## Future Extensions

While the core metrics are now protected, future updates may include:

- **Temperature Sensors**: Validating CPU/Modem temperature ranges if exposed by specific router models.
- **Client Latency**: Guarding against impossible ping/latency values for tracked clients.
