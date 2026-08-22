from zk import ZK

DEVICE_IP = "192.168.1.202"
DEVICE_PORT = 4370

zk = ZK(
    DEVICE_IP,
    port=DEVICE_PORT,
    timeout=10,
    password=0,
    force_udp=False
)

conn = None

try:
    print("Connecting to uFace302...")

    conn = zk.connect()

    print("SUCCESS: Connected to biometric device!")
    print()

    print("Device information")
    print("------------------")

    print("Firmware:", conn.get_firmware_version())
    print("Serial:", conn.get_serialnumber())
    print("Device name:", conn.get_device_name())
    print()

    print("Reading users...")

    users = conn.get_users()

    print("Total users:", len(users))
    print()

    for user in users:
        print(
            "UID:", user.uid,
            "| User ID:", user.user_id,
            "| Name:", user.name
        )

    print()
    print("Reading attendance records...")

    attendance = conn.get_attendance()

    print("Total attendance records:", len(attendance))
    print()

    for record in attendance:
        print(
            "UID:", record.uid,
            "| User ID:", record.user_id,
            "| Time:", record.timestamp,
            "| Status:", record.status,
            "| Punch:", record.punch
        )

except Exception as e:
    print("ERROR:")
    print(type(e).__name__)
    print(e)

finally:
    if conn:
        conn.disconnect()
        print()
        print("Disconnected from device.")