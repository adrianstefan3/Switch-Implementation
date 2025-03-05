#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

# Adresa MAC Broadcast
BROADCAST = "ff:ff:ff:ff:ff:ff"
# Adresa MAC Multicast
MULTICAST = b'\x01\x80\xc2\x00\x00\x00' #reprezentare hexa
MULTICAST_STR = "01:80:c2:00:00:00" #reprezentare string

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def create_bpdu_frame(root_id, root_path_cost_, bridge_id):
    # Ethernet Header
    frame = struct.pack("!6s", MULTICAST)
    frame += struct.pack("!6s", get_switch_mac())

    # LLC Length = 3(LLC Header) + 35(BPDU Header)
    frame += struct.pack("!H", 38)

    # LLC Header
    frame += struct.pack("!BBB", 0x42, 0x42, 0x03)

    # BPDU Header
    ## Protocol_id, Protocol_version, BPDU_type
    frame += struct.pack("!HBB", 0x0000, 0x00, 0x00)

    ## Flags
    frame += struct.pack("!B", 0x00)

    ## Root_id, Root_path_cost, Bridge_id
    frame += struct.pack("!Q", root_id)
    frame += struct.pack("!I", root_path_cost_)
    frame += struct.pack("!Q", bridge_id)

    ## Port_id
    frame += struct.pack("!H", 0x0000)

    ## Mess_age, Max_age, Hello_time, Forw_delay
    frame += struct.pack("!HHHH", 0, 20, 2, 15)

    return frame

def send_bdpu_every_sec(interfaces, sw_port_mode):
    frame = create_bpdu_frame(root_bridge_ID, root_path_cost, own_bridge_ID)
    length = len(frame)
    while True:
        # TODO Send BDPU every second if necessary
        if root_bridge_ID == own_bridge_ID:
            for intf in interfaces:
                if sw_port_mode[get_interface_name(intf)] == 'T':
                    send_to_link(intf, length, frame)
        time.sleep(1)

def is_unicast(addr):
    if addr == BROADCAST:
        return False
    
    # Primul octet din adresa MAC
    first_byte = int(addr[1], 16)

    # Adresele MAC Multicast au primul octet impar, iar cele Unicast par 
    if first_byte % 2 == 0:
        return True

    return False

def read_sw_config(switch_id):
    sw_port_mode = {}
    sw_priority = 0
    with open(f"configs/switch{switch_id}.cfg", "r") as f:
        configs = f.readlines()
        # Citire prioritate switch
        sw_priority = int(configs[0].strip())
        
        # Citire switchport modes
        for line in configs[1:]:
            temp = line.split()
            sw_port_mode[temp[0]] = temp[1]
    
    return sw_priority, sw_port_mode

def tag_frame(length, data, vlan_id, sw_port_mode, interface):
    tagged_frame = data
    if vlan_id == -1:
        vlan_id = int(sw_port_mode[get_interface_name(interface)])
        tagged_frame = data[0:12] + create_vlan_tag(vlan_id) + data[12:]
        length += 4
    return length, tagged_frame

def untag_frame(length, data, vlan_id, sw_port_mode, interface):
    untagged_frame = data
    if vlan_id != -1:
        untagged_frame = data[0:12] + data[16:]
        length -= 4
    return length, untagged_frame

def parse_bpdu_header(data):
    root_bridge_id = int.from_bytes(data[22:30], byteorder='big')
    root_path_cost = int.from_bytes(data[30:34], byteorder='big')
    bridge_id = int.from_bytes(data[34:42], byteorder='big')
    return root_bridge_id, root_path_cost, bridge_id

def send_broadcast_flooding(interfaces, interface, sw_port_mode, STP_sw_ports, tagged_frame, untagged_frame, v_id_src):
    for intf in interfaces:
        if intf != interface:
            # Trimit pe port Trunk:
            if sw_port_mode[get_interface_name(intf)] == 'T' and STP_sw_ports[intf] != 'B':
                send_to_link(intf, len(tagged_frame), tagged_frame)
            elif sw_port_mode[get_interface_name(intf)] != 'T':
                # Trimit pe port Access
                v_id_dst = int(sw_port_mode[get_interface_name(intf)])
                if v_id_src == v_id_dst:
                    send_to_link(intf, len(untagged_frame), untagged_frame)

def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    print("# Starting switch with id {}".format(switch_id), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    # Citire configuratii Switch
    sw_priority, sw_port_mode = read_sw_config(switch_id)

    # Initializare Tabela CAM
    CAM_Table = {}

    # Initializare STP
    STP_sw_ports = {}
    for intf in interfaces:
        if sw_port_mode[get_interface_name(intf)] == 'T':
            STP_sw_ports[intf] = 'B'
        else:
            STP_sw_ports[intf] = 'D'

    global own_bridge_ID, root_bridge_ID, root_path_cost
    own_bridge_ID = sw_priority
    root_bridge_ID = own_bridge_ID
    root_path_cost = 0
    root_port = -1

    if own_bridge_ID == root_bridge_ID:
        for intf in interfaces:
            STP_sw_ports[intf] = 'D'
            
    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec, args = (interfaces, sw_port_mode))
    t.start()

    # Printing interface names
    for i in interfaces:
        print(get_interface_name(i))

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Note. Adding a VLAN tag can be as easy as
        # tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')

        print("Received frame of size {} on interface {}".format(length, interface), flush=True)

        # Implementare STP:
        if dest_mac == MULTICAST_STR:
            i_am_root_bridge = 0
            bpdu_root_bridge_id, bpdu_root_path_cost, bpdu_bridge_id = parse_bpdu_header(data)
            if root_bridge_ID == own_bridge_ID:
                i_am_root_bridge = 1

            # Verificare daca s-a modificat Root Bridge-ul
            if bpdu_root_bridge_id < root_bridge_ID:
                root_bridge_ID = bpdu_root_bridge_id
                root_path_cost = bpdu_root_path_cost + 10
                root_port = interface
                
                # Verificare daca am fost Root Bridge
                if i_am_root_bridge == 1:
                    for intf in interfaces:
                        if intf != root_port and sw_port_mode[get_interface_name(intf)] == 'T':
                            STP_sw_ports[intf] = 'B'
                
                # Setare root_port pe Designated
                if root_port != -1 and STP_sw_ports[root_port] == 'B':
                    STP_sw_ports[root_port] = 'D'

                # Update and forward BPDU pe toate porturile trunk
                new_bpdu_frame = create_bpdu_frame(root_bridge_ID, root_path_cost, own_bridge_ID)
                bpdu_length = len(new_bpdu_frame)
                for intf in interfaces:
                    if intf != root_port and sw_port_mode[get_interface_name(intf)] == 'T':
                        send_to_link(intf, bpdu_length, new_bpdu_frame)
            
            elif bpdu_root_bridge_id == root_bridge_ID:
                if interface == root_port and bpdu_root_path_cost + 10 < root_path_cost:
                    root_path_cost = bpdu_root_path_cost + 10
                
                elif interface != root_port:
                    if bpdu_root_path_cost > root_path_cost:
                        if STP_sw_ports[interface] == 'B':
                            STP_sw_ports[interface] = 'D'
            
            elif bpdu_bridge_id == own_bridge_ID:
                STP_sw_ports[interface] = 'B'
            
            if own_bridge_ID == root_bridge_ID:
                for intf in interfaces:
                    if sw_port_mode[get_interface_name(intf)] == 'T':
                        STP_sw_ports[intf] = 'D'
        # Final implementare STP

        else:
            # Populare Tabela CAM
            CAM_Table[src_mac] = interface

            # Creare frame cu tag 802.1Q
            len_tag, tagged_frame = tag_frame(length, data, vlan_id, sw_port_mode, interface)
            # Creare frame fara tag 802.1Q
            len_untag, untagged_frame = untag_frame(length, data, vlan_id, sw_port_mode, interface)

            # Determinare VLAN ID din care face parte frame-ul
            v_id_src = vlan_id
            if vlan_id == -1:
                v_id_src = int(sw_port_mode[get_interface_name(interface)])

            if is_unicast(dest_mac):
                if dest_mac in CAM_Table:
                    dest_intf = CAM_Table[dest_mac]
                    # Trimit pe port Trunk:
                    if sw_port_mode[get_interface_name(dest_intf)] == 'T' and STP_sw_ports[dest_intf] != 'B':
                        send_to_link(dest_intf, len_tag, tagged_frame)
                    elif sw_port_mode[get_interface_name(dest_intf)] != 'T':
                        # Trimit pe port Access
                        v_id_dst = int(sw_port_mode[get_interface_name(dest_intf)])
                        if v_id_src == v_id_dst:
                            send_to_link(dest_intf, len_untag, untagged_frame)
                else:
                    send_broadcast_flooding(interfaces, interface, sw_port_mode, STP_sw_ports, tagged_frame, untagged_frame, v_id_src)
            else:
                send_broadcast_flooding(interfaces, interface, sw_port_mode, STP_sw_ports, tagged_frame, untagged_frame, v_id_src)

        # data is of type bytes.
        # send_to_link(i, length, data)

if __name__ == "__main__":
    main()
