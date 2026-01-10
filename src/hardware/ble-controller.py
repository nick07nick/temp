import asyncio
from bleak import BleakScanner, BleakClient

TARGET_NAME_PREFIX = "BF_"
UART_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"


async def run():
    print("--- BikeFit Debug Scanner ---")
    print("Searching for ANY device starting with 'BF_'...")

    # 1. Сканирование с выводом всего, что найдено
    devices = await BleakScanner.discover(timeout=5.0)

    target_device = None

    print(f"\nFound {len(devices)} devices total.")
    for d in devices:
        name = d.name or "Unknown"
        print(f" - [{d.address}] {name}")

        if name.startswith(TARGET_NAME_PREFIX):
            target_device = d

    if not target_device:
        print("\n❌ TARGET NOT FOUND.")
        print("Советы:")
        print("1. Потряси датчик (он мог уснуть).")
        print("2. Нажми Reset на плате.")
        return

    print(f"\n✅ MATCH FOUND: {target_device.name}")
    print("Connecting...")

    try:
        async with BleakClient(target_device) as client:
            print(f"Connected to {target_device.address}")

            # Сброс
            await client.write_gatt_char(UART_RX_UUID, b'0', response=True)
            print("Ready for commands. (1/0/q)")

            while True:
                cmd = await asyncio.to_thread(input, "> ")
                if cmd == '1':
                    await client.write_gatt_char(UART_RX_UUID, b'1', response=True)
                    print("ON")
                elif cmd == '0':
                    await client.write_gatt_char(UART_RX_UUID, b'0', response=True)
                    print("OFF")
                elif cmd == 'q':
                    break

    except Exception as e:
        print(f"Connection Error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass