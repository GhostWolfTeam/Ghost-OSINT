# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        GO_badpackets
# Purpose:     ghostosint plugin to search Bad Packets API for any
#              malicious activity by the target
#
# Author:      Krishnasis Mandal <krishnasis@hotmail.com>
#
# Created:     11/05/2020
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import urllib.error
import urllib.parse
import urllib.request

from netaddr import IPNetwork

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_badpackets(GhostOsintPlugin):

    meta = {
        'name': "Bad Packets——恶意数据包",
        'summary': "获取有关发现的涉及 IP 地址的任何恶意活动的信息",
        'flags': ["apikey"],
        'useCases': ["Investigate", "Passive"],
        'categories': ["Reputation Systems"],
        'dataSource': {
            'website': "https://badpackets.net",
            'model': "COMMERCIAL_ONLY",
            'references': [
                "https://docs.badpackets.net/"
            ],
            'apiKeyInstructions': [
                "访问 https://badpackets.net/pricing/",
                "选择月计划",
                "填写联系表格",
                "BadPackets 将使用你的 API 密钥联系你"
            ],
            'favIcon': "https://i1.wp.com/badpackets.net/wp-content/uploads/2019/04/cropped-512x512_logo.png?fit=32%2C32&ssl=1",
            'logo': "https://badpackets.net/wp-content/uploads/2019/05/badpackets-rgb-350x70.png",
            'description': "Bad Packets 通过持续监控和检测恶意活动，提供关于新出现威胁、DDoS僵尸网络和网络滥用的网络威胁情报. "
            "我们由经验丰富的安全专业人员组成的团队进行全面的道德研究，以确保我们的数据具有最高的质量和准确性.\n"
            "通过不断汇总和分析相关数据，我们可以为合作伙伴提供可采取行动的信息，以主动防御新出现的安全威胁.",
        }
    }

    opts = {
        'api_key': '',
        'checkaffiliates': True,
        'subnetlookup': False,
        'netblocklookup': True,
        'maxnetblock': 24,
        'maxsubnet': 24
    }

    # Option descriptions. Delete any options not applicable to this module.
    optdescs = {
        "api_key": "Bad Packets API 密钥",
        'checkaffiliates': "检查关联公司?",
        'subnetlookup': "查找目标所属子网上的所有 IP 地址?",
        'netblocklookup': "在目标的网段上查找所有 IP 地址，以查找同一目标子域或域上可能被列入黑名单的主机?",
        'maxnetblock': "如果查找拥有的网段，则为查找其中所有IP的最大网段大小 (CIDR 值, 24 = /24, 16 = /16, 等等.)",
        'maxsubnet': "如果正在查找子网，则为要在其中查找所有IP的最大子网划分 (CIDR 值, 24 = /24, 16 = /16, 等等.)"
    }

    results = None
    errorState = False
    limit = 100

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events does this module accept for input
    # For a list of all events, check sfdb.py.
    def watchedEvents(self):
        return ["IP_ADDRESS", "NETBLOCK_OWNER", "NETBLOCK_MEMBER",
                "AFFILIATE_IPADDR"]

    # What events this module produces
    def producedEvents(self):
        return ["IP_ADDRESS", "MALICIOUS_IPADDR", "RAW_RIR_DATA",
                "MALICIOUS_AFFILIATE_IPADDR"]

    # Check whether the IP Address is malicious using Bad Packets API
    # https://docs.badpackets.net/#operation/query
    def queryIPAddress(self, qry, currentOffset):
        params = {
            'source_ip_address': qry.encode('raw_unicode_escape').decode("ascii", errors='replace'),
            'limit': self.limit,
            'offset': currentOffset
        }

        headers = {
            'Accept': "application/json",
            'Authorization': "Token " + self.opts['api_key']
        }

        res = self.GhostOsint.fetchUrl(
            'https://api.badpackets.net/v1/query?' + urllib.parse.urlencode(params),
            headers=headers,
            timeout=15,
            useragent=self.opts['_useragent']
        )

        return self.parseAPIResponse(res)

    # Parse API Response from Bad Packets
    def parseAPIResponse(self, res):
        if res['content'] is None:
            self.info("No Bad Packets information found")
            return None

        # Error codes as mentioned in Bad Packets Documentation
        if res['code'] == '400':
            self.error("Invalid IP Address")
            return None

        if res['code'] == '401':
            self.error("Unauthorized API Key")
            return None

        if res['code'] == '403':
            self.error("Forbidden Request")
            return None

        # Catch all non-200 status codes, and presume something went wrong
        if res['code'] != '200':
            self.error("Failed to retrieve content from Bad Packets")
            return None

        # Always always always process external data with try/except since we cannot
        # trust the data is as intended.
        try:
            return json.loads(res['content'])
        except Exception as e:
            self.error(f"Error processing JSON response from Bad Packets: {e}")
            return None

        return None

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if self.errorState:
            return

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        # Always check if the API key is set and complain if it isn't, then set
        # self.errorState to avoid this being a continual complaint during the scan.
        if self.opts['api_key'] == "":
            self.error("You enabled GO_badpackets but did not set an API key!")
            self.errorState = True
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        if eventName == 'NETBLOCK_OWNER':
            if not self.opts['netblocklookup']:
                return

            if IPNetwork(eventData).prefixlen < self.opts['maxnetblock']:
                self.debug(f"Network size bigger than permitted: {IPNetwork(eventData).prefixlen} > {self.opts['maxnetblock']}")
                return

        if eventName == 'NETBLOCK_MEMBER':
            if not self.opts['subnetlookup']:
                return

            if IPNetwork(eventData).prefixlen < self.opts['maxsubnet']:
                self.debug(f"Network size bigger than permitted: {IPNetwork(eventData).prefixlen} > {self.opts['maxsubnet']}")
                return

        qrylist = list()
        if eventName.startswith("NETBLOCK_"):
            for ipaddr in IPNetwork(eventData):
                qrylist.append(str(ipaddr))
                self.results[str(ipaddr)] = True
        else:
            # If user has enabled affiliate checking
            if eventName == "AFFILIATE_IPADDR" and not self.opts['checkaffiliates']:
                return
            qrylist.append(eventData)

        for addr in qrylist:

            nextPageHasData = True
            if self.checkForStop():
                return

            currentOffset = 0
            while nextPageHasData:
                data = self.queryIPAddress(addr, currentOffset)

                if data is None:
                    nextPageHasData = False
                    break

                count = data.get('count')
                if count is None or int(count) == 0:
                    nextPageHasData = False
                    break

                # Data is reported about the IP Address
                if eventName.startswith("NETBLOCK_"):
                    ipEvt = GhostOsintEvent("IP_ADDRESS", addr, self.__name__, event)
                    self.notifyListeners(ipEvt)

                records = data.get('results')
                if records is None:
                    nextPageHasData = False
                    break

                if records:
                    if eventName.startswith("NETBLOCK_"):
                        evt = GhostOsintEvent("RAW_RIR_DATA", str(records), self.__name__, ipEvt)
                        self.notifyListeners(evt)
                    else:
                        evt = GhostOsintEvent("RAW_RIR_DATA", str(records), self.__name__, event)
                        self.notifyListeners(evt)

                    for record in records:
                        maliciousIP = record.get('source_ip_address')

                        if maliciousIP != addr:
                            self.error("Reported address doesn't match requested, skipping.")
                            continue

                        if maliciousIP:
                            maliciousIPDesc = "Bad Packets [" + str(maliciousIP) + "]\n"

                            try:
                                category = record.get('tags')[0].get('category')
                                if category:
                                    maliciousIPDesc += " - CATEGORY : " + str(category) + "\n"
                            except Exception:
                                self.debug("No category found for target")

                            try:
                                description = record.get('tags')[0].get('description')
                                if description:
                                    maliciousIPDesc += " - DESCRIPTION : " + str(description) + "\n"
                            except Exception:
                                self.debug("No description found for target")

                            maliciousIPDescHash = self.GhostOsint.hashstring(maliciousIPDesc)
                            if maliciousIPDescHash in self.results:
                                continue
                            self.results[maliciousIPDescHash] = True

                            # If target is a netblock_ report current IP address as target
                            if eventName.startswith("NETBLOCK_"):
                                evt = GhostOsintEvent("MALICIOUS_IPADDR", maliciousIPDesc, self.__name__, ipEvt)
                            elif eventName.startswith("AFFILIATE_"):
                                evt = GhostOsintEvent("MALICIOUS_AFFILIATE_IPADDR", maliciousIPDesc, self.__name__, event)
                            else:
                                evt = GhostOsintEvent("MALICIOUS_IPADDR", maliciousIPDesc, self.__name__, event)

                            self.notifyListeners(evt)

                if records is None or data.get('count') < self.limit or len(records) < self.limit:
                    nextPageHasData = False
                currentOffset += self.limit

# End of GO_badpackets class
