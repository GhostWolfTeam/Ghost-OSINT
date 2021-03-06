# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         GO_virustotal
# Purpose:      Query VirusTotal for identified IP addresses.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     21/03/2014
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from netaddr import IPNetwork

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_virustotal(GhostOsintPlugin):

    meta = {
        'name': "VirusTotal",
        'summary': "从 VirusTotal 获取有关IP地址的信息.",
        'flags': ["apikey"],
        'useCases': ["Investigate", "Passive"],
        'categories': ["Reputation Systems"],
        'dataSource': {
            'website': "https://www.virustotal.com/",
            'model': "FREE_AUTH_LIMITED",
            'references': [
                "https://developers.virustotal.com/reference"
            ],
            'apiKeyInstructions': [
                "访问 https://www.virustotal.com/",
                "注册一个免费账户",
                "点击你的个人资料",
                "点击 API Key",
                "API 密钥将在 'API Key'"
            ],
            'favIcon': "https://www.virustotal.com/gui/images/favicon.png",
            'logo': "https://www.virustotal.com/gui/images/logo.svg",
            'description': "分析可疑文件和URL以检测恶意软件类型，并自动与安全社区共享.",
        }
    }

    opts = {
        'api_key': '',
        'verify': True,
        'publicapi': True,
        'checkcohosts': True,
        'checkaffiliates': True,
        'netblocklookup': True,
        'maxnetblock': 24,
        'subnetlookup': True,
        'maxsubnet': 24
    }

    optdescs = {
        'api_key': 'VirusTotal API 密钥.',
        'publicapi': '你使用的是公钥吗？如果是这样，GhostOSINT 将在每次查询后暂停15秒，以避免 VirusTotal 丢弃请求.',
        'checkcohosts': '检查共同托管的网站?',
        'checkaffiliates': '检查关联公司?',
        'netblocklookup': '在目标的网段上查找同一目标子域或域上可能存在的主机的所有IP地址?',
        'maxnetblock': '如果查找网段，则为查找其中所有IP的最大网段的大小 (CIDR 值, 24 = /24, 16 = /16, 等等.)',
        'subnetlookup': '查找目标所属子网上的所有IP地址?',
        'maxsubnet': '如果查询子网则设置子网最大的子网划分 (CIDR 值, 24 = /24, 16 = /16, 等等.)',
        'verify': '验证在目标域名上找到的任何主机名是否仍可解析?'
    }

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return [
            "IP_ADDRESS",
            "AFFILIATE_IPADDR",
            "INTERNET_NAME",
            "CO_HOSTED_SITE",
            "NETBLOCK_OWNER",
            "NETBLOCK_MEMBER"
        ]

    def producedEvents(self):
        return [
            "MALICIOUS_IPADDR",
            "MALICIOUS_INTERNET_NAME",
            "MALICIOUS_COHOST",
            "MALICIOUS_AFFILIATE_INTERNET_NAME",
            "MALICIOUS_AFFILIATE_IPADDR",
            "MALICIOUS_NETBLOCK",
            "MALICIOUS_SUBNET",
            "INTERNET_NAME",
            "AFFILIATE_INTERNET_NAME",
            "INTERNET_NAME_UNRESOLVED",
            "DOMAIN_NAME"
        ]

    def queryIp(self, qry):
        params = urllib.parse.urlencode({
            'ip': qry,
            'apikey': self.opts['api_key'],
        })

        res = self.GhostOsint.fetchUrl(
            f"https://www.virustotal.com/vtapi/v2/ip-address/report?{params}",
            timeout=self.opts['_fetchtimeout'],
            useragent="GhostOSINT"
        )

        # Public API is limited to 4 queries per minute
        if self.opts['publicapi']:
            time.sleep(15)

        if res['content'] is None:
            self.info(f"No VirusTotal info found for {qry}")
            return None

        try:
            return json.loads(res['content'])
        except Exception as e:
            self.error(f"Error processing JSON response from VirusTotal: {e}")
            self.errorState = True

        return None

    def queryDomain(self, qry):
        params = urllib.parse.urlencode({
            'domain': qry,
            'apikey': self.opts['api_key'],
        })

        res = self.GhostOsint.fetchUrl(
            f"https://www.virustotal.com/vtapi/v2/domain/report?{params}",
            timeout=self.opts['_fetchtimeout'],
            useragent="GhostOSINT"
        )

        if res['code'] == "204":
            self.error("Your request to VirusTotal was throttled.")
            return None

        # Public API is limited to 4 queries per minute
        if self.opts['publicapi']:
            time.sleep(15)

        if res['content'] is None:
            self.info(f"No VirusTotal info found for {qry}")
            return None

        try:
            return json.loads(res['content'])
        except Exception as e:
            self.error(f"Error processing JSON response from VirusTotal: {e}")
            self.errorState = True

        return None

    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if self.errorState:
            return

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if self.opts["api_key"] == "":
            self.error(
                f"You enabled {self.__class__.__name__} but did not set an API key!"
            )
            self.errorState = True
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        if eventName.startswith("AFFILIATE") and not self.opts['checkaffiliates']:
            return

        if eventName == 'CO_HOSTED_SITE' and not self.opts['checkcohosts']:
            return

        if eventName == 'NETBLOCK_OWNER':
            if not self.opts['netblocklookup']:
                return

            net_size = IPNetwork(eventData).prefixlen
            max_netblock = self.opts['maxnetblock']
            if net_size < max_netblock:
                self.debug(f"Network size {net_size} bigger than permitted: {max_netblock}")
                return

        if eventName == 'NETBLOCK_MEMBER':
            if not self.opts['subnetlookup']:
                return

            net_size = IPNetwork(eventData).prefixlen
            max_subnet = self.opts['maxsubnet']
            if net_size < max_subnet:
                self.debug(f"Network size {net_size} bigger than permitted: {max_subnet}")
                return

        qrylist = list()
        if eventName.startswith("NETBLOCK_"):
            for ipaddr in IPNetwork(eventData):
                qrylist.append(str(ipaddr))
                self.results[str(ipaddr)] = True
        else:
            qrylist.append(eventData)

        for addr in qrylist:
            if self.checkForStop():
                return

            if self.GhostOsint.validIP(addr):
                info = self.queryIp(addr)
            else:
                info = self.queryDomain(addr)

            if info is None:
                continue

            if len(info.get('detected_urls', [])) > 0:
                self.info(f"Found VirusTotal URL data for {addr}")

                if eventName in ["IP_ADDRESS"] or eventName.startswith("NETBLOCK_"):
                    evt = "MALICIOUS_IPADDR"
                    infotype = "ip-address"

                if eventName == "AFFILIATE_IPADDR":
                    evt = "MALICIOUS_AFFILIATE_IPADDR"
                    infotype = "ip-address"

                if eventName == "INTERNET_NAME":
                    evt = "MALICIOUS_INTERNET_NAME"
                    infotype = "domain"

                if eventName == "AFFILIATE_INTERNET_NAME":
                    evt = "MALICIOUS_AFFILIATE_INTERNET_NAME"
                    infotype = "domain"

                if eventName == "CO_HOSTED_SITE":
                    evt = "MALICIOUS_COHOST"
                    infotype = "domain"

                infourl = f"<SFURL>https://www.virustotal.com/en/{infotype}/{addr}/information/</SFURL>"

                e = GhostOsintEvent(
                    evt, f"VirusTotal [{addr}]\n{infourl}",
                    self.__name__,
                    event
                )
                self.notifyListeners(e)

            domains = list()

            # Treat siblings as affiliates if they are of the original target, otherwise
            # they are additional hosts within the target.
            if 'domain_siblings' in info:
                if eventName in ["IP_ADDRESS", "INTERNET_NAME"]:
                    for domain in info['domain_siblings']:
                        domains.append(domain)

            if 'subdomains' in info:
                if eventName == "INTERNET_NAME":
                    for domain in info['subdomains']:
                        domains.append(domain)

            for domain in set(domains):
                if domain in self.results:
                    continue

                if self.getTarget().matches(domain):
                    evt_type = 'INTERNET_NAME'
                else:
                    evt_type = 'AFFILIATE_INTERNET_NAME'

                if self.opts['verify'] and not self.GhostOsint.resolveHost(domain) and not self.GhostOsint.resolveHost6(domain):
                    self.debug(f"Host {domain} could not be resolved")
                    evt_type += '_UNRESOLVED'

                evt = GhostOsintEvent(evt_type, domain, self.__name__, event)
                self.notifyListeners(evt)

                if self.GhostOsint.isDomain(domain, self.opts['_internettlds']):
                    if evt_type.startswith('AFFILIATE'):
                        evt = GhostOsintEvent('AFFILIATE_DOMAIN_NAME', domain, self.__name__, event)
                        self.notifyListeners(evt)
                    else:
                        evt = GhostOsintEvent('DOMAIN_NAME', domain, self.__name__, event)
                        self.notifyListeners(evt)

# End of GO_virustotal class
