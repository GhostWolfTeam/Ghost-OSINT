# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         GO_vxvault
# Purpose:      Check if a domain or IP address is malicious according to VXVault.net.
#
# Author:       steve@binarypool.com
#
# Created:     14/12/2013
# Copyright:   (c) Steve Micallef, 2013
# Licence:     GPL
# -------------------------------------------------------------------------------

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_vxvault(GhostOsintPlugin):

    meta = {
        'name': "VXVault.net",
        'summary': "根据 vxvault.net 检查域名或 IP地址 是否是恶意的.",
        'flags': [],
        'useCases': ["Investigate", "Passive"],
        'categories': ["Reputation Systems"],
        'dataSource': {
            'website': "http://vxvault.net/",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [
                "http://vxvault.net/URL_List.php",
                "https://github.com/InfectedPacket/VxVault"
            ],
            'favIcon': "",
            'logo': "http://vxvault.net/header.png",
            'description': "VxVault 是一个恶意软件管理程序，用于自动下载和分类恶意软件样本. "
            "VxVault 从网页或 RSS 提要等在线来源的链接下载恶意软件示例，下载它们并尝试使用 VirusTotal 识别恶意软件. "
            "然后将恶意软件分类到本地文件系统和 SQLite 数据库中.",
        }
    }

    # Default options
    opts = {
        'checkaffiliates': True,
        'checkcohosts': True,
        'cacheperiod': 18
    }

    # Option descriptions
    optdescs = {
        'checkaffiliates': "检查关联企业?",
        'checkcohosts': "检查目标 IP地址 上共同托管的站点?",
        'cacheperiod': "之前缓存数据提取."
    }

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()
        self.errorState = False

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    def watchedEvents(self):
        return [
            "INTERNET_NAME",
            "IP_ADDRESS",
            "IPV6_ADDRESS",
            "AFFILIATE_IPADDR",
            "AFFILIATE_IPV6_ADDRESS",
            "AFFILIATE_INTERNET_NAME",
            "CO_HOSTED_SITE"
        ]

    # What events this module produces
    def producedEvents(self):
        return [
            "MALICIOUS_IPADDR",
            "MALICIOUS_INTERNET_NAME",
            "MALICIOUS_AFFILIATE_IPADDR",
            "MALICIOUS_AFFILIATE_INTERNET_NAME",
            "MALICIOUS_COHOST"
        ]

    def queryBlacklist(self, target):
        blacklist = self.retrieveBlacklist()

        if not blacklist:
            return False

        if target.lower() in blacklist:
            self.debug(f"Host name {target} found in VXVault.net blacklist.")
            return True

        return False

    def retrieveBlacklist(self):
        blacklist = self.GhostOsint.cacheGet('vxvault', 24)

        if blacklist is not None:
            return self.parseBlacklist(blacklist)

        res = self.GhostOsint.fetchUrl(
            "http://vxvault.net/URL_List.php",
            timeout=10,
            useragent=self.opts['_useragent'],
        )

        if res['code'] != "200":
            self.error(f"Unexpected HTTP response code {res['code']} from VXVault.net.")
            self.errorState = True
            return None

        if res['content'] is None:
            self.error("Received no content from VXVault.net")
            self.errorState = True
            return None

        self.GhostOsint.cachePut("vxvault", res['content'])

        return self.parseBlacklist(res['content'])

    def parseBlacklist(self, blacklist):
        """Parse plaintext blacklist

        Args:
            blacklist (str): plaintext blacklist from VXVault.net

        Returns:
            list: list of blacklisted IP addresses and host names
        """
        hosts = list()

        if not blacklist:
            return hosts

        for line in blacklist.split('\n'):
            if not line:
                continue
            if not line.startswith('http'):
                continue

            # Note: URL parsing and validation with GhostOsint.validHost() is too slow to use here
            url = line.strip().lower()
            if len(url.split("/")) < 3:
                continue
            host = url.split("/")[2]
            if not host:
                continue
            if "." not in host and "::" not in host:
                continue
            hosts.append(host)

        return hosts

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        if self.errorState:
            return

        self.results[eventData] = True

        if eventName.startswith("AFFILIATE") and not self.opts['checkaffiliates']:
            return

        if eventName == 'CO_HOSTED_SITE' and not self.opts.get('checkcohosts'):
            return

        if eventName in ['IP_ADDRESS', 'IPV6_ADDRESS']:
            evtType = 'MALICIOUS_IPADDR'
        elif eventName in ['AFFILIATE_IPADDR', 'AFFILIATE_IPV6_ADDRESS']:
            evtType = 'MALICIOUS_AFFILIATE_IPADDR'
        elif eventName == "INTERNET_NAME":
            evtType = "MALICIOUS_INTERNET_NAME"
        elif eventName == 'AFFILIATE_INTERNET_NAME':
            evtType = 'MALICIOUS_AFFILIATE_INTERNET_NAME'
        elif eventName == 'CO_HOSTED_SITE':
            evtType = 'MALICIOUS_COHOST'
        else:
            return

        self.debug(f"Checking maliciousness of {eventData} ({eventName}) with VXVault.net")

        if self.queryBlacklist(eventData):
            url = "http://vxvault.net/URL_List.php"
            text = f"VXVault Malicious URL List [{eventData}]\n<SFURL>{url}</SFURL>"
            evt = GhostOsintEvent(evtType, text, self.__name__, event)
            self.notifyListeners(evt)

# End of GO_vxvault class
