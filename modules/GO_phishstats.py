# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        GO_phishstats
# Purpose:     ghostosint plugin to search PhishStats API
#              to determine if an IP is malicious.
#
# Author:      Krishnasis Mandal <krishnasis@hotmail.com>
#
# Created:     18/05/2020
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import urllib.error
import urllib.parse
import urllib.request

from netaddr import IPNetwork

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_phishstats(GhostOsintPlugin):

    meta = {
        'name': "PhishStats",
        'summary': "根据 PhishStats 检查网段或IP地址是否为恶意地址.",
        'flags': [],
        'useCases': ["Investigate", "Passive"],
        'categories': ["Reputation Systems"],
        'dataSource': {
            'website': "https://phishstats.info/",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [
                "https://phishstats.info/#apidoc"
            ],
            'favIcon': "https://phishstats.info/phish.ico",
            'description': "PhishStats 是一个实时网络钓鱼数据库，从多个来源收集网络钓鱼 Url 地址.",
        }
    }

    opts = {
        'checkaffiliates': True,
        'netblocklookup': True,
        'maxnetblock': 24,
        'subnetlookup': True,
        'maxsubnet': 24,
    }

    optdescs = {
        'checkaffiliates': "检查关联企业?",
        'netblocklookup': "在目标的网段上查找所有 IP 地址，以查找同一目标子域或域上可能被列入黑名单的主机?",
        'maxnetblock': "如果查找网段，则为查找其中所有IP的最大网段的大小 (CIDR 值, 24 = /24, 16 = /16, 等等.)",
        'subnetlookup': "查找目标子网上的所有IP地址是否在黑名单中?",
        'maxsubnet': "如果查询子网则设置子网最大的子网划分 (CIDR 值, 24 = /24, 16 = /16, 等等.)",
    }

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()
        self.errorState = False

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return [
            'IP_ADDRESS',
            'AFFILIATE_IPADDR',
            "NETBLOCK_MEMBER",
            "NETBLOCK_OWNER",
        ]

    def producedEvents(self):
        return [
            "BLACKLISTED_IPADDR",
            "BLACKLISTED_AFFILIATE_IPADDR",
            "BLACKLISTED_SUBNET",
            "BLACKLISTED_NETBLOCK",
            "MALICIOUS_IPADDR",
            "MALICIOUS_AFFILIATE_IPADDR",
            "MALICIOUS_NETBLOCK",
            "MALICIOUS_SUBNET",
            "RAW_RIR_DATA",
        ]

    # Check whether the IP address is malicious using PhishStats API
    # https://phishstats.info/
    def queryIPAddress(self, qry):
        params = {
            '_where': f"(ip,eq,{qry})",
            '_size': 1
        }

        headers = {
            'Accept': "application/json",
        }

        res = self.GhostOsint.fetchUrl(
            'https://phishstats.info:2096/api/phishing?' + urllib.parse.urlencode(params),
            headers=headers,
            timeout=15,
            useragent=self.opts['_useragent']
        )

        if res['code'] != "200":
            self.debug(f"No information found from PhishStats for {qry}.")
            return None

        try:
            return json.loads(res['content'])
        except Exception as e:
            self.error(f"Error processing JSON response: {e}")

        return None

    def handleEvent(self, event):
        eventName = event.eventType
        eventData = event.data

        if self.errorState:
            return

        self.debug(f"Received event, {eventName}, from {event.module}")

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        if eventName == 'AFFILIATE_IPADDR':
            if not self.opts.get('checkaffiliates', False):
                return
            malicious_type = "MALICIOUS_AFFILIATE_IPADDR"
            blacklist_type = "BLACKLISTED_AFFILIATE_IPADDR"
        elif eventName == 'IP_ADDRESS':
            malicious_type = "MALICIOUS_IPADDR"
            blacklist_type = "BLACKLISTED_IPADDR"
        elif eventName == 'NETBLOCK_MEMBER':
            if not self.opts['subnetlookup']:
                return

            max_subnet = self.opts['maxsubnet']
            if IPNetwork(eventData).prefixlen < max_subnet:
                self.debug(f"Network size bigger than permitted: {IPNetwork(eventData).prefixlen} > {max_subnet}")
                return

            malicious_type = "MALICIOUS_SUBNET"
            blacklist_type = "BLACKLISTED_SUBNET"
        elif eventName == 'NETBLOCK_OWNER':
            if not self.opts['netblocklookup']:
                return

            max_netblock = self.opts['maxnetblock']
            if IPNetwork(eventData).prefixlen < max_netblock:
                self.debug(f"Network size bigger than permitted: {IPNetwork(eventData).prefixlen} > {max_netblock}")
                return

            malicious_type = "MALICIOUS_NETBLOCK"
            blacklist_type = "BLACKLISTED_NETBLOCK"
        else:
            self.debug(f"Unexpected event type {eventName}, skipping")
            return

        qrylist = list()
        if eventName.startswith("NETBLOCK"):
            for ipaddr in IPNetwork(eventData):
                qrylist.append(str(ipaddr))
                self.results[str(ipaddr)] = True
        else:
            qrylist.append(eventData)

        for addr in qrylist:
            if self.checkForStop():
                return

            data = self.queryIPAddress(addr)

            if not data:
                continue

            # TODO: iterate through hosts and extract co-hosts
            try:
                maliciousIP = data[0].get('ip')
            except Exception:
                # If ArrayIndex is out of bounds then data doesn't exist
                continue

            if not maliciousIP:
                continue

            if addr != maliciousIP:
                self.error(f"Reported address {maliciousIP} doesn't match queried IP address {addr}, skipping")
                continue

            # For netblocks, we need to create the IP address event so that
            # the threat intel event is more meaningful.
            if eventName == 'NETBLOCK_OWNER':
                pevent = GhostOsintEvent("IP_ADDRESS", addr, self.__name__, event)
                self.notifyListeners(pevent)
            elif eventName == 'NETBLOCK_MEMBER':
                pevent = GhostOsintEvent("AFFILIATE_IPADDR", addr, self.__name__, event)
                self.notifyListeners(pevent)
            else:
                pevent = event

            evt = GhostOsintEvent("RAW_RIR_DATA", str(data), self.__name__, pevent)
            self.notifyListeners(evt)

            text = f"PhishStats [{addr}]"

            evt = GhostOsintEvent(blacklist_type, text, self.__name__, pevent)
            self.notifyListeners(evt)

            evt = GhostOsintEvent(malicious_type, text, self.__name__, pevent)
            self.notifyListeners(evt)

# End of GO_phishstats class
