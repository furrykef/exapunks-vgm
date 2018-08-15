# Some assumptions:
# No channels disabled
# No envelopes
# No sweeps
# Two length counter ticks per NTSC frame
# Length counter or linear counter of 0 mutes channel, even if the counter's not enabled
import math
import textwrap
import struct
import sys
import vgmparse


PULSE1 = 0
PULSE2 = 1
TRI = 2
NOISE = 3

SAMPLES_PER_FRAME = 1470

NOISE_TBL = [100, 100, 100, 100, 90, 90, 90, 90, 80, 80, 80, 80, 70, 70, 70, 70]

LENGTH_TBL = [10,254, 20,  2, 40,  4, 80,  6, 160,  8, 60, 10, 14, 12, 26, 14,
              12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30]


class Note(object):
    def __init__(self, pitch, duration):
        self.pitch = pitch
        self.duration = duration


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    infilename, outfilename = argv

    with open(infilename, 'rb') as f:
        vgm_data = vgmparse.Parser(f.read())

    channels = process_vgm(vgm_data)

    with open(outfilename, 'w') as f:
        for i, channel in enumerate(channels):
            print("*** CHANNEL", i, file=f)
            byte_list = []
            for note in channel:
                byte_list.append(str(note.pitch))
                byte_list.append(str(note.duration))
            byte_list.append("0 0")
            byte_str = " ".join(byte_list)
            f.write(textwrap.fill(byte_str,
                                  24,
                                  initial_indent="DATA ",
                                  subsequent_indent="DATA "))
            f.write("\n\n\n")


def process_vgm(vgm_data):
    channels = [[Note(0, 0)] for i in range(4)]
    channel_regs = [[0]*4 for i in range(4)]
    reg4015 = 0
    length_counters = [0]*4
    linear_counter_reload = 0
    clock = 0

    for command in vgm_data.command_list:
        cmd = ord(command['command'])
        data = command['data']
        if 0x61 <= cmd <= 0x63 or 0x70 <= cmd <= 0x7f:
            # This is a wait
            if cmd == 0x61:
                wait_time = struct.unpack('<H', data)[0]
            elif cmd == 0x62:
                wait_time = 735
            elif cmd == 0x63:
                wait_time = 882
            else:
                wait_time = cmd - 0x70
            clock += wait_time
            while clock >= SAMPLES_PER_FRAME:
                # End of Redshift frame
                for i in range(4):
                    vol = 15 if i == TRI else channel_regs[i][0] & 0x0f
                    if length_counters[i] == 0:
                        vol = 0
                    if vol == 0:
                        pitch = 0
                    else:
                        if i == NOISE:
                            pitch = noise_pitch(channel_regs[i][2] & 0x0f)
                        else:
                            period = ((channel_regs[i][3] & 0x07) << 8) | channel_regs[i][2]
                            if i == TRI:
                                period *= 2
                            pitch = period_to_pitch(period)
                    last_note = channels[i][-1]
                    if pitch == last_note.pitch and last_note.duration < 9999:
                        last_note.duration += 1
                    else:
                        channels[i].append(Note(pitch, 1))
                    if channel_regs[i][0] & 0x80 == 0:
                        # Length counter is active; clock it
                        length_counters[i] = max(length_counters[i] - 1, 0)
                clock -= SAMPLES_PER_FRAME
        elif cmd == 0xb4:
            # APU register write
            reg, byte = data
            if reg < 0x10:
                # We're writing to one of our channels
                chan_id = reg//4
                chan_reg = reg%4
                channel_regs[chan_id][chan_reg] = byte
                if chan_reg == 0 and chan_id == TRI:
                    # Set linear counter reload value
                    if byte == 0:
                        linear_counter_reload = 0
                    else:
                        linear_counter_reload = max(((byte & 0x7f)+4)/8, 1)
                if chan_reg == 3:
                    length = LENGTH_TBL[byte >> 3]
                    length = max((length+2)/4, 1)
                    if chan_id == TRI:
                        length = min(length, linear_counter_reload)
                    length_counters[chan_id] = length
            elif reg == 0x15:
                reg4015 = byte
        elif cmd == 0x66:
            # End of data
            break
        else:
            print("Unsupported command: 0x%02X" % cmd, file=sys.stderr)

    return channels


# Pitches are actually MIDI note numbers
def period_to_pitch(period):
    hz = 1789773/(16*(period+1))
    return int(round(69 + 12 * math.log2(hz / 440)))


def noise_pitch(period):
    return int(NOISE_TBL[period])


if __name__ == '__main__':
    sys.exit(main())
