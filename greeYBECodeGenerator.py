from io import StringIO
import sys
import tuya

# --- Constants (placeholders) ---
POWER_OFF = 0
POWER_ON = 1
MODE_AUTO, MODE_HEAT, MODE_COOL, MODE_DRY, MODE_FAN = range(5)
VDIR_AUTO, VDIR_SWING, VDIR_UP, VDIR_MUP, VDIR_MIDDLE, VDIR_MDOWN, VDIR_DOWN = range(7)
HDIR_AUTO, HDIR_SWING, HDIR_LEFT, HDIR_MLEFT, HDIR_MIDDLE, HDIR_MRIGHT, HDIR_RIGHT = range(7)

GREE_AIRCON1_POWER_ON = 0x08
GREE_AIRCON1_POWER_OFF = 0
GREE_AIRCON1_MODE_AUTO = 1
GREE_AIRCON1_MODE_HEAT = 0x04
GREE_AIRCON1_MODE_COOL = 3
GREE_AIRCON1_MODE_DRY = 4
GREE_AIRCON1_MODE_FAN = 5


GREE_AIRCON_FAN_AUTO =  0x00 # Fan speed
GREE_AIRCON_FAN1     = 0x10 # * low
GREE_AIRCON_FAN2     = 0x20 # * med
GREE_AIRCON_FAN_HIGH     = 0x30 # * high
GREE_AIRCON_FAN_TURBO    = 0x80 # * turbo mode

GREE_AIRCON1_FAN_X = 0x60
GREE_AIRCON1_FAN_Y = 0x10

GREE_VDIR_AUTO = 0
GREE_HDIR_AUTO = 0


def convert_params(powerModeCmd, operatingModeCmd, fanSpeed, temperatureCmd,
                   swingVCmd, swingHCmd, turboMode, iFeelMode):
    """Convert human command parameters into encoded IR parameters."""

    # Defaults
    powerMode = GREE_AIRCON1_POWER_ON
    operatingMode = GREE_AIRCON1_MODE_HEAT
    temperature = 21
    swingV = GREE_VDIR_AUTO
    swingH = GREE_HDIR_AUTO

    if powerModeCmd == POWER_OFF:
        powerMode = GREE_AIRCON1_POWER_OFF
    else:
        # Map operating mode
        if operatingModeCmd == MODE_AUTO:
            operatingMode = GREE_AIRCON1_MODE_AUTO
            temperatureCmd = 25
        elif operatingModeCmd == MODE_HEAT:
            operatingMode = GREE_AIRCON1_MODE_HEAT
        elif operatingModeCmd == MODE_COOL:
            operatingMode = GREE_AIRCON1_MODE_COOL
        elif operatingModeCmd == MODE_DRY:
            operatingMode = GREE_AIRCON1_MODE_DRY
            fanSpeed = GREE_AIRCON1_FAN_AUTO 
        elif operatingModeCmd == MODE_FAN:
            operatingMode = GREE_AIRCON1_MODE_FAN


    # Vertical swing
    swingV = {
        VDIR_AUTO: GREE_VDIR_AUTO,
        VDIR_SWING: 1,
        VDIR_UP: 2,
        VDIR_MUP: 3,
        VDIR_MIDDLE: 4,
        VDIR_MDOWN: 5,
        VDIR_DOWN: 6
    }.get(swingVCmd, GREE_VDIR_AUTO)

    # Horizontal swing
    swingH = {
        HDIR_AUTO: GREE_HDIR_AUTO,
        HDIR_SWING: 1,
        HDIR_LEFT: 2,
        HDIR_MLEFT: 3,
        HDIR_MIDDLE: 4,
        HDIR_MRIGHT: 5,
        HDIR_RIGHT: 6
    }.get(swingHCmd, GREE_HDIR_AUTO)

    # Temperature valid range
    if 15 < temperatureCmd < 31:
        temperature = temperatureCmd - 16

    return {
        "powerMode": powerMode,
        "operatingMode": operatingMode,
        "fanSpeed": fanSpeed,
        "temperature": temperature,
        "swingV": swingV,
        "swingH": swingH
    }

def generate_command_yap(
    powerMode, operatingMode, fanSpeed, temperature,
    swingV, swingH, turboMode, iFeelMode,
    light, xfan, health, valve,
    sthtMode, enableWiFi
):
    """
    Python equivalent of:
      void GreeYAPHeatpumpIR::generateCommand(...)

    Builds a 24-byte IR command buffer for Gree YAP heatpump models.
    """

    # Base command (equivalent to calling GreeiFeelHeatpumpIR::generateCommand)
    # In Python, we’ll initialize and fill basic 8-byte header manually.
    buffer = [0] * 24  # 24-byte total

    # --- Simulate the parent generateCommand() content ---
    # (this sets basic power/mode/fan/temperature structure)
    buffer[0] = fanSpeed | operatingMode | powerMode
    buffer[1] = temperature
    # buffer[2]..[7] will be overwritten below per YAP-specific rules.

    # --- YAP-specific fields ---
    buffer[2] = (
        (1 << 4 if turboMode else 0)
        | (1 << 5 if light else 0)
        | (1 << 6 if health else 0)
        | (1 << 7 if xfan else 0)
    )

    # Bits 4..7 always 0101 (0x50), bit0 optionally valve
    buffer[3] = 0x50 | (1 << 0 if valve else 0)

    # Combine vertical + horizontal swing
    buffer[4] = swingV | (swingH << 4)

    # Bit7 always set; add iFeel + WiFi bits
    buffer[5] = (
        0x80
        | (1 << 2 if iFeelMode else 0)
        | (1 << 6 if enableWiFi else 0)
    )

    # Bit2 = sthtMode
    buffer[7] = (1 << 2) if sthtMode else 0

    # --- Copy and zero extended areas ---
    # memset(buffer + 8, 0, 16)  → zero bytes 8..23 (already zeroed by initialization)
    # memcpy(buffer + 8, buffer, 3)  → copy first 3 bytes into bytes 8–10
    buffer[8:11] = buffer[0:3]

    # --- Add repeated constant fields ---
    buffer[8 + 3] = 0x70 | (1 << 0 if valve else 0)  # buffer[11]
    buffer[16 + 3] = 0xA0                            # buffer[19]
    buffer[16 + 7] = 0xA0                            # buffer[23]

    return buffer

def calculate_checksum(buffer):
    """Calculate Gree checksum as in original code."""
    checksum = (
        (
            (buffer[0] & 0x0F)
            + (buffer[1] & 0x0F)
            + (buffer[2] & 0x0F)
            + (buffer[3] & 0x0F)
            + ((buffer[4] & 0xF0) >> 4)
            + ((buffer[5] & 0xF0) >> 4)
            + ((buffer[6] & 0xF0) >> 4)
            + 0x0A
        ) & 0x0F
    ) << 4
    buffer[7] = (buffer[7] & 0x0F) | checksum
    return buffer


def generate_command(powerMode, operatingMode, fanSpeed, temperature,
                     swingV, swingH, turboMode, iFeelMode):
    """Simulate building an 8-byte IR frame."""
    buffer = [0] * 8

    # Fan + mode + power bits
    buffer[0] = fanSpeed | operatingMode | powerMode

    # Temperature
    buffer[1] = temperature

    # Simplified extensions could follow for specific remotes (YAA, YAN, etc.)
    # Here we just return the basic frame
    return buffer


def send_yap(
    IR,
    powerModeCmd, operatingModeCmd,
    fanSpeedCmd, temperatureCmd,
    swingVCmd, swingHCmd,
    turboMode, iFeelMode,
    light, xfan,
    health, valve,
    sthtMode, enableWiFi
):
    """
    Python equivalent of:
      void GreeYAPHeatpumpIR::send(...)

    This function prepares IR command parameters, generates the full IR frame,
    and sends it via an abstract IR sender interface.
    """

    # --- Step 1: Convert input command parameters ---
    params = convert_params(
        powerModeCmd, operatingModeCmd, fanSpeedCmd, temperatureCmd,
        swingVCmd, swingHCmd, turboMode, iFeelMode
    )

    powerMode = params["powerMode"]
    operatingMode = params["operatingMode"]
    fanSpeed = params["fanSpeed"]
    temperature = params["temperature"]
    swingV = params["swingV"]
    swingH = params["swingH"]

    # --- Step 2: Generate the Gree YAP command frame ---
    buffer = generate_command_yap(
        powerMode, operatingMode,
        fanSpeed, temperature,
        swingV, swingH,
        turboMode, iFeelMode,
        light, xfan, health,
        valve, sthtMode, enableWiFi
    )

    # --- Step 3: Calculate checksums (simulate both primary and secondary blocks) ---
    buffer = calculate_checksum(buffer)
    buffer = calculate_checksum(buffer[8:])  # mimic buffer + 8

    # --- Step 4: Send or print the frame ---
    # In C++, this would call: sendBuffer(IR, buffer, 24)
    # Here, we simulate sending.
    if hasattr(IR, "send"):
        IR.send(buffer)
    else:
        print("Sending IR frame (YAP):", [b for b in buffer])

    return buffer

def send_buffer(IR, buffer, timings):
    """
    Python equivalent of:
      void GreeHeatpumpIR::sendBuffer(IRSender& IR, const uint8_t * buffer, size_t len)

    Simulates sending IR data frames in groups of 8 bytes using the Gree protocol.
    `IR` should provide the same methods as the C++ IRSender object:
        - setFrequency(freq_khz)
        - mark(duration)
        - space(duration)
        - sendIRbyte(byte_value, bit_mark, zero_space, one_space)
    """

    length = len(buffer)

    # --- 1. Set IR carrier frequency (38 kHz) ---
    IR.setFrequency(38)
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    # --- 2. Iterate through 8-byte message chunks ---
    for pos in range(0, length, 8):
        # All but the first group must be preceded by a space
        if pos != 0:
            IR.mark(timings["bit_mark"])
            IR.space(timings["msg_space"])

        # --- Header mark and space ---
        IR.mark(timings["hdr_mark"])
        IR.space(timings["hdr_space"])

        # --- Payload part #1 (bytes 0–3) ---
        for i in range(4):
            IR.sendIRbyte(
                buffer[pos + i],
                timings["bit_mark"],
                timings["zero_space"],
                timings["one_space"]
            )

        # --- Three fixed bits of byte 4 ("010") ---
        IR.mark(timings["bit_mark"]); IR.space(timings["zero_space"])
        IR.mark(timings["bit_mark"]); IR.space(timings["one_space"])
        IR.mark(timings["bit_mark"]); IR.space(timings["zero_space"])

        # --- Message space separator ---
        IR.mark(timings["bit_mark"])
        IR.space(timings["msg_space"])

        # --- Payload part #2 (bytes 4–7) ---
        for i in range(4, 8):
            IR.sendIRbyte(
                buffer[pos + i],
                timings["bit_mark"],
                timings["zero_space"],
                timings["one_space"]
            )

        # --- End mark ---
        IR.mark(timings["bit_mark"])
        IR.space(0)
    
    sys.stdout = old_stdout
    return mystdout.getvalue()


# Sends current sensed temperatures, YAC remotes/supporting units only

def sendIFeel(ir, current_temperature):
    gree_template = [0x00, 0x00]

    gree_template[0] = current_temperature
    gree_template[1] = 0xA5

    # 38 kHz PWM frequency
    ir.setFrequency(38)

    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()

    # Send Header mark
    ir.mark(timings["ifeel_hdr_mark"])
    ir.space(timings["ifeel_hdr_space"])

    # Send payload
    ir.sendIRbyte(
        gree_template[0],
        timings["ifeel_bit_mark"],
        timings["zero_space"],
        timings["one_space"]
    )

    ir.sendIRbyte(
        gree_template[1],
        timings["ifeel_bit_mark"],
        timings["zero_space"],
        timings["one_space"]
    )

    # End mark
    ir.mark(timings["ifeel_bit_mark"])
    ir.space(0)

    sys.stdout = old_stdout
    return mystdout.getvalue()


class MockIRSender:
    def setFrequency(self, freq):
        print(f"[IR] Set frequency to {freq} kHz")

    def mark(self, duration):
        # print(f"[IR] MARK {duration} µs")
        print(f"{duration},", end='');

    def space(self, duration):
        print(f"{duration},", end='');
        # print(f"[IR] SPACE {duration} µs")


    def sendIRbyte(IR, send_byte, bit_mark_length, zero_space_length, one_space_length, bit_count=8):
        """
        Python equivalent of:
          void IRSender::sendIRbyte(uint8_t sendByte, int bitMarkLength, int zeroSpaceLength, int oneSpaceLength, uint8_t bitCount)

           Sends a single byte (LSB first) using mark/space modulation.
    
        Parameters:
          IR                - an object providing mark() and space() methods
          send_byte         - integer (0–255)
          bit_mark_length   - duration of a "mark" (µs)
           zero_space_length - space duration for a 0-bit (µs)
           one_space_length  - space duration for a 1-bit (µs)
          bit_count         - number of bits to send (default 8)
         """

        for _ in range(bit_count):
            if send_byte & 0x01:
                IR.mark(bit_mark_length)
                IR.space(one_space_length)
            else:
                IR.mark(bit_mark_length)
                IR.space(zero_space_length)
            send_byte >>= 1


# Example timings dictionary, similar to C++ struct
timings = {
    "hdr_mark": 9000,
    "hdr_space": 4500,
    "bit_mark": 650,
    "one_space": 1643,
    "zero_space": 510,
    "msg_space": 20000,
    "ifeel_hdr_mark": 6000,
    "ifeel_hdr_space": 3000,
    "ifeel_bit_mark": 650
}

# Simulate buffer of 8 bytes (one qframe)
# buffer = [0x10, 0x15, 0x20, 0x00, 0xA0, 0xB0, 0xC0, 0x00]



params = convert_params(
    powerModeCmd=POWER_ON, operatingModeCmd=MODE_HEAT, fanSpeed=GREE_AIRCON_FAN_HIGH,
    temperatureCmd=21, swingVCmd=VDIR_SWING, swingHCmd=HDIR_SWING,
    turboMode=False, iFeelMode=False,
)

frame = generate_command_yap(**params, turboMode=False, iFeelMode=True, light=False, xfan=False, health=False, valve=False, sthtMode=False, enableWiFi=False)
frame = calculate_checksum(frame)


# Run simulation
IR = MockIRSender()
result = send_buffer(IR, frame, timings)
source = [int(x) for x in result.rstrip(",").split(",")]

lenghts=[50 if x==0 else x for x in source]
print(tuya.encode_ir(lenghts))

print("IR frame:", [x for x in frame])

iFeelLenghts = sendIFeel(IR, 19)
sourceIFeelSplit = [int(x) for x in iFeelLenghts.rstrip(",").split(",")]
sourceIFeel=[50 if x==0 else x for x in sourceIFeelSplit]

print("IR singnal legnths IFeel: ", sourceIFeel)

print("IR Code: ", tuya.encode_ir(sourceIFeel))
