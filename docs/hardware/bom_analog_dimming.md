# Production BOM: Active Marker v2.5 (Flicker-Free Edition)

**Target:** Sunlight readable, Wide Angle, No-PWM Dimming.
**Method:** Dual-channel resistive driver (20mA / 60mA / 80mA).
**PCB:** Round Ø17.0 mm.

## 1. Key Components Changes

| Role | Part Number (LCSC) | Component Name | Package | Notes |
|------|--------------------|----------------|---------|-------|
| **Dual MOSFET** | **C15426** | **MBR360** (или аналог **2N7002DW**) | **SOT-363** | Два N-MOSFET в одном корпусе (6 ног). Экономит место. |
| **Wide LED** | **C97262** | **VSMY2850G** | SMD 1206 | **Angle: 120° (±60°)**. Идеально для трекинга сбоку. |
| **Resistor A** | **Generic** | **100R (100 Ohm)** | 0805 | Для режима Low Power (Indoor). |
| **Resistor B** | **Generic** | **33R (33 Ohm)** | **1206** | Для режима High Power. 1206 обязательно (греется!). |
| **MCU** | **C133036** | **nRF52832-QFAA-R** | QFN-48 | Main Brain. |
| **Accel** | **C97767** | **LIS2DH12TR** | LGA-12 | Wake-up sensor. |
| **Charger**| **C15068** | **MCP73831T-2ACI/OT**| SOT-23-5 | Charging IC (Set to 40mA). |
| **LDO** | **C5446** | **XC6206P302MR** | SOT-23 | 3.0V Regulator for MCU only. |
| **Antenna**| **C137151** | **2450AT18B100E** | 1206 | Керамическая антенна Johanson. |

## 2. Schematic Logic (Flicker-Free Driver)

Вместо одного ключа мы строим два параллельных пути тока через один LED.

### 2.1 Connections
1.  **Battery (+)** подключена к Аноду LED.
2.  **Катод LED** раздваивается на два пути:
    * **Путь 1:** Резистор **100 Ом** -> MOSFET A (Drain).
    * **Путь 2:** Резистор **33 Ом** -> MOSFET B (Drain).
3.  Истоки (Sources) обоих MOSFET -> GND.
4.  Затворы (Gates) -> К двум разным пинам nRF52 (через резисторы 100 Ом).

### 2.2 Logic Table (Firmware Control)

| Mode | Pin A (P0.xx) | Pin B (P0.yy) | Current (approx) | Use Case | Battery Life |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **OFF** | LOW | LOW | 0 mA | Sleep | Months |
| **LOW** | **HIGH** | LOW | ~20 mA | Evening / Indoor | ~5-6 Hours |
| **MED** | LOW | **HIGH** | ~60 mA | Cloudy Day | ~2 Hours |
| **MAX** | **HIGH** | **HIGH** | ~80 mA | **Direct Sunlight** | ~1 Hour |

*Расчет тока для LIR1654 (V_bat=3.7V, V_led=1.5V, Drop=2.2V):*
* Low: 2.2V / 100R = 22 mA.
* Med: 2.2V / 33R = 66 mA.
* Max: 22 mA + 66 mA = 88 mA (реально чуть меньше из-за просадки батареи).

## 3. Thermal Management
В режиме MAX на резисторе 33 Ом выделяется: $P = I^2 * R = 0.066^2 * 33 = 0.14 W$.
Резистор 1206 держит 0.25W. Запас есть, но он будет теплым.
**Layout Requirement:** Сделайте большие медные полигоны вокруг резистора 33 Ом для охлаждения.