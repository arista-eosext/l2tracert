#!/usr/bin/env python
#
# Copyright (c) 2015, Arista Networks, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#  - Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#  - Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#  - Neither the name of Arista Networks nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#L2TRACERT
#
#    Version 1.2  - 7/21/2015 
#    Written by: 
#       Jeremy Georges - Arista Networks
#       jgeorges@arista.com
#
#    Revision history:
#       1.0 - initial release - 4/29/2015
#       1.1 - Added MAC and VLAN validation. Fixed minor bug. - 5/5/2015
#       1.2 - Added additional logic for Port-channels - 7/21/2015

""" l2tracert 
    The purpose of this script is to provide a traceroute function but at layer 2. The user must specify a destination MAC address
    and a VLAN. Additionally, LLDP must be enabled between the switches and they must leverage EAPI.
    If LLDP and or EAPI is not enabled, the script will stop at that switch hop.

    Additionally, the ma1 interface must have an IP and all neighbor Arista switches need to be reachable via the ma1 interface,
    since this is the IP that shows up in the LLDP management IP field.
    
    The script uses the output of the 'show mac address-table' command and LLDP information to build a hop by hop representation 
    of the l2 route from beginning to final egress switch port.
    In large Layer 2 environments, this can be helpful to understand each switch and physical interface  that is used to reach 
    a specific mac address, especially when troubleshooting.

    A user account must be created that has enough privilege to run the 'show mac address-table' and 'show lldp' commands.
    Either the variables DEFAULTUSER and DEFAULTPW will need to be set or command line arguments can be specified.

    To make it easier to execute from EOS, an alias can be setup to provide those required authentication paramenters.
    For example:
    7050S-64(config)#alias l2trace bash /mnt/flash/l2tracert.py -u admin -p mypassword 
    
    Now the alias l2trace can be used instead of having to type the username and password each time.
    7050S-64#l2trace -m 000e.c687.8c93 -v 1
    L2 Trace Route to 000e.c687.8c93 on VLAN 1
    
    Hop          Host             Egress           Remote Host      Ingress
    ********************************************************************************
    1            7050S-64         Ethernet49/1     7050QX           Ethernet49/1
    2            7050QX           Ethernet33       7048-LAB-R1      Ethernet49
    3            7048-LAB-R1      Ethernet48       NA

   INSTALLATION:
   Copy to the /mnt/flash directory of each Arista switch that you want to use l2tracert.

"""

VERSION='1.1'
DEFAULTUSER='admin'
DEFAULTPW='4me2know'


#=====================================================
# Variables
#=====================================================



#***********************************************************************************
# Modules
#***********************************************************************************
import os
import re
import sys
import optparse
import syslog
from jsonrpclib import Server


#==========================================================
# Function Definitions
#==========================================================
def matchme(strg, pattern):
    search=re.compile(pattern).search
    return bool(search(strg))

def macchk(mac):
    import re
    #Check mac format to be in the form of 0000.0000.0000
    # This is the format used in EOS
    if re.match("[0-9a-f]{4}([.])[0-9a-f]{4}(\\1[0-9a-f]{4}){1}$", mac.lower()):
       return 1
    else:
       return 0

def switchparse(switch,mac,vlan):  
    '''
    switchparse function parses output of show mac address table and show lldp neighbor details.
    It will return a list that can be used to print out the next hop info if its exists.
    '''
    try:
        showhostname = switch.runCmds( 1,[ "enable","show hostname" ],"json")
    except:
        #Return 0 and we'll use this to determine that we can't connect.
        #Probably because EAPI is not enabled!
        return 0

    try:
        showmactable = switch.runCmds( 1,[ "enable","show mac address-table address %s vlan %s" % (mac, vlan) ],"json")
    except:
        return 0
  
    try:
        #If this throws an exception, it means the mac address is not there...
        egressinterface=showmactable[1]['unicastTable']['tableEntries'][0]['interface']
    except:
        #Return 1 and we'll use this to determine that MAC is not found
        # Return 1 because if we returned 0 above, that means we couldn't connect
        return 1 
    #Lets create an empty list that will hold the following items:
    #  -egress interface
    #  -Neighbor Port ID
    #  -System Name
    #  -Management Address
    #  -System Description
    #  -Hostname of device queried.
    #
    # If the System Description is "Arista Networks EOS", lets change it to "Arista"
    # If the Management Address is blank, just set it to "NA"
    # If the System Description is something other than Arista, we'll leave it alone.
    # The reason for this, we can't parse the next neighbor since this script is written around EOS constructs. 
    # Therefore, if the System Description is not set to Arista, we'll assume its the end host we're actually trying to 
    # do the l2trace route on. If its another switch, then user will have to manually look at that other switch to see if there
    # are any more next hop switches to analyze. But they should be able to ascertain this by the 'system name'.
 
    lldplist=[]
    # Since the show lldp neighbors command does not support port-channels (since this is a link level protocol)
    # we need to add additional logic to check the lldp neighbor of one of the member interfaces of the port-channel.
    # That should be sufficient for our needs.
    
    if re.findall("Ethernet.*", egressinterface): 
        lldplist.append(("".join(egressinterface)))  
        showlldpneighbor = switch.runCmds( 1,[ "enable","show lldp neighbors %s detail" % (egressinterface) ],"text")
        switchneighbor=showlldpneighbor[1] ["output"]
    elif re.findall("Port-Channel.*", egressinterface):
        #We need to look at the LLDP neighbor on just one member interface. Lets just look at the first one, that
        #should be sufficient. 
        try:
            showportchannel = switch.runCmds( 1,[ "enable","show interfaces %s " % (egressinterface) ],"json")
        except:
            print "Issue with parsing Port Channel Members"
            return 0 
        #First member interface listed should be listed as first one
        phyegressinterfaces=showportchannel[1]['interfaces'][egressinterface]['memberInterfaces'].keys()[0]
        #append the egressint to our list which will be displayed as the port-channel here.
        lldplist.append(("".join(egressinterface)))
        #Here we need to override that and use the first member interface of our port-channel for the lldp 
        #neighbor command.
        showlldpneighbor = switch.runCmds( 1,[ "enable","show lldp neighbors %s detail" % (phyegressinterfaces) ],"text")
        switchneighbor=showlldpneighbor[1] ["output"]

    if  re.findall("Port ID     :.*", switchneighbor):
        currentneighborport = re.findall("Port ID     :.*", switchneighbor)
    else: 
        #This means the next device doesn't have LLDP enabled...so we'll just have to stuff an NA flag here.
        currentneighborport = "NA"
        #We'll just fall through the logic below if we have NA flagged.

    #Ok we need to strip out the field label and whitespace
    currentneighborport = map(lambda currentneighborport:currentneighborport.replace("Port ID     : ", ""),currentneighborport)
    #Strip out the quotes now...
    currentneighborport = map(lambda currentneighborport:currentneighborport.replace("\"", ""),currentneighborport)
    # Append our list with a string form of our final modified output :-)
    lldplist.append(("".join(currentneighborport)))

    # Now parse for System Name
    if re.findall("System Name:.*", switchneighbor):
        currentneighborsystemname = re.findall("System Name:.*", switchneighbor)
    else:
        currentneighborsystemname = "NA"
    #Ok we need to strip out the field label and whitespace
    currentneighborsystemname = map(lambda currentneighborsystemname:currentneighborsystemname.replace("System Name: ", ""),currentneighborsystemname)
    #Strip out the quotes now
    currentneighborsystemname = map(lambda currentneighborsystemname:currentneighborsystemname.replace("\"", ""),currentneighborsystemname)
    # Append our list with a string form of our final modified output :-)
    lldplist.append(("".join(currentneighborsystemname)))

    #Now parse for Management Address
    if re.findall("Management Address        :.*", switchneighbor):
        currentneighbormgmtaddress = re.findall("Management Address        :.*", switchneighbor)
    else:
        currentneighbormgmtaddress = "NA"
    #Ok we need to strip out the field label and whitespace
    currentneighbormgmtaddress = map(lambda currentneighbormgmtaddress:currentneighbormgmtaddress.replace("Management Address        : ", ""),currentneighbormgmtaddress)
    #Strip out the quotes now
    currentneighbormgmtaddress = map(lambda currentneighbormgmtaddress:currentneighbormgmtaddress.replace("\"", ""),currentneighbormgmtaddress)
    # Append our list with a string form of our final modified output :-)
    lldplist.append(("".join(currentneighbormgmtaddress)))

    #Finally, parse for System Description
    #
    #We're going to make things simple here. If we regex and find 'Arista Networks EOS', we'll just set this list item to 'Arista'
    #That way, we'll have some logic to know if we can actually query the next host. If its not Arista...then we'll just show the egress
    #interface.
    # The logic for this will be checked in the main section of script. 
    if re.findall("System Description:.*", switchneighbor) and re.findall("Arista Networks EOS.*", switchneighbor):
        currentneighbordescription = 'Arista' 
    else:
        currentneighbordescription = "NA"
    # Append our list with a string form of our final modified output :-)
    lldplist.append(("".join(currentneighbordescription)))
    
    # Add the current hostname as the final element. 
    lldplist.append(("".join(showhostname[1]['hostname'])))
    return (lldplist)



#==========================================================
# MAIN
#==========================================================

def main():
    usage = "usage: %prog [options] arg1 arg2"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option("-V", "--version", action="store_true",dest="version", help="The version")
    parser.add_option("-v", "--vlan", type="string", dest="vlan", help="Vlan that MAC resides on",metavar="VLAN")
    parser.add_option("-m", "--mac", type="string", dest="mac", help="MAC Address to Traceroute on",metavar="MAC")
    parser.add_option("-d", action="store_true", dest="verbose", help="Verbose logging")
    parser.add_option("-u", "--user", type="string", dest="USERNAME", help="Username for EAPI",metavar="username",default=DEFAULTUSER)
    parser.add_option("-p", "--password", type="string", dest="PASSWORD", help="Password for EAPI",metavar="password",default=DEFAULTPW)
    (options, args) = parser.parse_args()

    if options.version:
        print os.path.basename(sys.argv[0]), "  Version: ", VERSION 
        sys.exit(0)

    # Do some simple validation of mac and vlan id
    if options.vlan and options.mac:
        if not macchk(options.mac):
            print "MAC format not valid. You must enter MAC in the following format:  aaaa.bbbb.cccc"
            sys.exit(0) 
        if not (0 < int(options.vlan) < 4095):
            print "VLAN ID not correct"
            sys.exit(0)
    else:
        print "VLAN & MAC address required as arguments to execute l2tracert"
        sys.exit(0)

   
    # General login setup
    localswitch = Server( "https://%s:%s@127.0.0.1/command-api" % (options.USERNAME,options.PASSWORD))
    #remoteswitch = Server( "https://%s:%s@%s/command-api" % (options.USERNAME,options.PASSWORD,remote_IP))
    
    # switchparse function takes 3 arguments and returns a list with the following:
    # - egress interface
    #  -Neighbor Port ID
    #  -System Name
    #  -Management Address
    #  -System Description 
    #  - hostname being queried

    local=switchparse(localswitch,options.mac,options.vlan) 
    if local == 1:
        # If the first hop (local switch) returns a 0, then MAC address doesn't exist on switch.
        print "MAC Address not found!"
        sys.exit(0)
    if local == 0:
        # This means EAPI failed!
        print "EAPI Request Failed."
        sys.exit(0)

    # Set iteration to 1, increment on each run. 
    iteration=1
    #Need to setup print function here!
    print "L2 Trace Route to %s on VLAN %s" % (options.mac, options.vlan)
    print " "
    print "{0:12} {1:16} {2:16} {3:16} {4:16}".format("Hop","Host", "Egress", "Remote Host" , "Ingress")
    print "*"*80
    iteration=1
    print "{0:12} {1:16} {2:16} {3:16} {4:16}".format(str(iteration),local[5], local[0], local[2] , local[1])
    # Go into a loop and we'll break out of the loop if we get a System Description that is not "Arista" 
    remote_IP=local[3]
    while True:
        iteration += 1
        remoteswitch = Server( "https://%s:%s@%s/command-api" % (options.USERNAME,options.PASSWORD,remote_IP))
        remote=switchparse(remoteswitch,options.mac,options.vlan) 
        #import pdb; pdb.set_trace() 
        if remote == 0:
           print "Appears that the next switch does not have EAPI enabled."
           sys.exit(0)
        elif remote == 1:
            print "MAC not found on remote switch %s. Try pinging the destination address first." % remote_IP
            break 
        elif remote[4] == 'Arista':
            print "{0:12} {1:16} {2:16} {3:16} {4:16}".format(str(iteration),remote[5], remote[0], remote[2] , remote[1])
            remote_IP=remote[3]
        else:
            print "{0:12} {1:16} {2:16} {3:16} {4:16}".format(str(iteration),remote[5], remote[0], remote[2] , " ")
            break


if __name__ == "__main__":
    main()
