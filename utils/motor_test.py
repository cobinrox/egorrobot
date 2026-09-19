import can
import time

MOTOR_ID = 0x7F  # Default CyberGear ID (127)
MASTER_ID = 0x00

def send_frame(bus, cmd_type, data_bytes=None):
    if data_bytes is None:
        data_bytes = [0] * 8
    # Bits 28-24: Command Type | Bits 23-8: Master ID | Bits 7-0: Target Motor ID
    can_id = (cmd_type << 24) | (MASTER_ID << 8) | MOTOR_ID
    msg = can.Message(arbitration_id=can_id, data=data_bytes, is_extended_id=True)
    try:
        bus.send(msg)
        print(f"Sent CAN Frame ID: 0x{can_id:08X}")
    except can.CanError as e:
        print(f"Failed to send frame: {e}")

# Context manager ensures SocketCAN bus is properly shut down on exit
with can.interface.Bus(channel='can0', bustype='socketcan', bitrate=1000000) as bus:
    print("1. Enabling Motor...")
    send_frame(bus, 0x03)  # Command 3: Enable motor
    time.sleep(1)

    # Listen for status reply from motor
    reply = bus.recv(timeout=2.0)
    if reply:
        print(f"Motor Response Received! ID: 0x{reply.arbitration_id:08X}, Data: {reply.data.hex()}")
    else:
        print("No response from motor. Check power, motor ID, or termination resistance.")

    print("2. Disabling Motor...")
    send_frame(bus, 0x04)  # Command 4: Reset/Stop motor