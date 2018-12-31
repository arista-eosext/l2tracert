# l2tracert


The purpose of this script is to provide a traceroute function but at layer 2 specifically across Arista switches. 


# Author
Jeremy Georges - Arista Networks   - jgeorges@arista.com

# Description
The l2tracert script provides a mechanism to traceroute a path through Arista switches at layer 2. By using a combination of 
the output of the 'show mac address-table' command and LLDP Neighbor information, the targeted MAC address can be
analyzed on a hop-by-hop (switch-by-switch) basis. The script output provides an layer 2 route from beginning to final egress switch port.
In large Layer 2 environments, this can be helpful to understand each switch and physical interface  that is used to reach
a specific mac address, especially when troubleshooting.

The current implementation requires both a target VLAN and the MAC address in the format of aaaa.bbbb.cccc which is the format
of the MAC address entries in EOS specifically in the 'show mac address-table' output.

Additionally, LLDP must be enabled between the switches and they must leverage EAPI.
If LLDP and or EAPI is not enabled, the script will stop at that switch hop and provide output that EAPI is not enabled on that switch.

Additionally, the ma1 interface must have an IP and all neighbor Arista switches need to be reachable via the ma1 interface,
since this is the IP that shows up in the LLDP management IP field.


A user account must be created that has enough privilege to run the 'show mac address-table' and 'show lldp' commands.
Either the variables DEFAULTUSER and DEFAULTPW will need to be set in the script or command line arguments can be specified.

To make it easier to execute from EOS, an alias can be setup to provide those required authentication parameters.
For example:


    7050S-64(config)#alias l2trace bash /mnt/flash/l2tracert.py -u admin -p mypassword


Now the alias l2trace can be used instead of having to type the username and password each time.<br>


    7050S-64#l2trace -m 000e.c687.8c93 -v 1
    L2 Trace Route to 000e.c687.8c93 on VLAN 1

    Hop          Host             Egress           Remote Host      Ingress
    ********************************************************************************
    1            7050S-64         Ethernet49/1     7050QX           Ethernet49/1
    2            7050QX           Ethernet33       7048-LAB-R1      Ethernet49
    3            7048-LAB-R1      Ethernet48       NA

## Example

### Output if MAC is not learned


    [admin@7050S-64 flash]$ ./l2tracert.py -m 000e.c687.8c93 -v 1 -u admin -p 4me2know
    MAC Address not found!


### Ping it first so mac is learned...


    [admin@7050S-64 flash]$ ping 192.168.100.4
    PING 192.168.100.4 (192.168.100.4) 56(84) bytes of data.
    64 bytes from 192.168.100.4: icmp_req=1 ttl=128 time=0.767 ms

    [admin@7050S-64 flash]$ ./l2tracert.py -m 000e.c687.8c93 -v 1
    L2 Trace Route to 000e.c687.8c93 on VLAN 1
 
    Hop          Host             Egress           Remote Host      Ingress         
    ********************************************************************************
    1            7050S-64         Ethernet49/1     7050QX           Ethernet49/1    
    2            7050QX           Ethernet33       7048-LAB-R1      Ethernet49      
    Appears that the next switch does not have EAPI enabled.


## Enable EAP on the last switch 7048...


    [admin@7050S-64 flash]$ ./l2tracert.py -u admin -p 4me2know -m 000e.c687.8c93 -v 1
    L2 Trace Route to 000e.c687.8c93 on VLAN 1
 
    Hop          Host             Egress           Remote Host      Ingress         
    ********************************************************************************
    1            7050S-64         Ethernet49/1     7050QX           Ethernet49/1    
    2            7050QX           Ethernet33       7048-LAB-R1      Ethernet49      
    3            7048-LAB-R1      Ethernet48       NA                               


# INSTALLATION:
Copy to the /mnt/flash directory of each Arista switch that you want to use l2tracert.



License
=======
BSD-3, See LICENSE file
