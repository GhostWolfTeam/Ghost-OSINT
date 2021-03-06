# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         GO_socialprofiles
# Purpose:      Tries to discover social media profiles of any identified human names.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     12/04/2014
# Copyright:   (c) Steve Micallef 2014
# Licence:     GPL
# -------------------------------------------------------------------------------

import re
import urllib.error
import urllib.parse
import urllib.request

from ghostosint import GhostOsintEvent, GhostOsintPlugin

sites = {
    # Search string to use, domain name the profile will sit on within
    # those search results.
    "Facebook": [
        "\"{name}\"+site:facebook.com",
        [
            r'[ \'"](https?://[a-z\.]*facebook.[a-z\.]+/[^/"\'<> ]+/?)[\'"]',
            r'(https?%3a%2f%2f[a-z\.]*facebook.[a-z\.]+%2f[^\/"\'<> ]+/?)',
        ],
    ],
    "Google+": [
        "\"{name}\"+site:plus.google.com",
        [
            r'[ \'"](https?://plus.google.[a-z\.]+/\d+[^"\'<>\/ ]+)[\'"]',
            r'(https?%3a%2f%2fplus.google.[a-z\.]+%2f\d+[^\/"\'<> ]+)',
        ],
    ],
    "LinkedIn": [
        "\"{name}\"+site:linkedin.com",
        [
            r'["\' ](https?://[a-z\.]*linkedin.[a-z\.]+/[^\?"\'<> ]+)[\'"]',
            r'(https?%3a%2f%2f[a-z\.]*linkedin.[a-z\.]+%2f[^\?"\'<> ]+)',
        ],
    ],
}


class GO_socialprofiles(GhostOsintPlugin):

    meta = {
        'name': "社交媒体个人资料查找器",
        'summary': "查找已识别人名的社交媒体资料.",
        'flags': ["slow", "apikey"],
        'useCases': ["Footprint", "Passive"],
        'categories': ["Social Media"],
        'dataSource': {
            'website': "https://developers.google.com/custom-search",
            'model': "FREE_AUTH_LIMITED",
            'references': [
                "https://developers.google.com/custom-search/v1",
                "https://developers.google.com/custom-search/docs/overview",
                "https://cse.google.com/cse"
            ],
            'apiKeyInstructions': [
                "如果使用 Google:",
                "访问 https://developers.google.com/custom-search/v1/introduction",
                "注册一个免费的 Google 账户",
                "点击 'Get A Key'",
                "连接项目",
                "API 密钥将在 'YOUR API KEY'",
                "如果使用 Bing:",
                "访问 https://azure.microsoft.com/en-in/services/cognitive-services/bing-web-search-api/",
                "注册一个免费账户",
                "选择 Bing 自定义搜索",
                "API 密钥将在 'Key1' 和 'Key2' (两个都可以使用)"
            ],
            'favIcon': "https://www.gstatic.com/devrel-devsite/prod/v2210deb8920cd4a55bd580441aa58e7853afc04b39a9d9ac4198e1cd7fbe04ef/developers/images/favicon.png",
            'logo': "https://www.gstatic.com/devrel-devsite/prod/v2210deb8920cd4a55bd580441aa58e7853afc04b39a9d9ac4198e1cd7fbe04ef/developers/images/favicon.png",
            'description': "Google 自定义搜索使你能够为你的网站、博客或网站集合创建搜索引擎. "
            "你可以将引擎配置为同时搜索网页和图像. "
            "你可以微调排名，添加自己的促销活动，自定义搜索结果的外观和感觉. "
            "你可以通过将你的搜索引擎连接到你的谷歌 AdSense 帐户来赚钱.",
        }
    }

    # Default options
    opts = {
        "count": 20,
        "method": "bing",
        "tighten": True,
        "bing_api_key": "",
        "google_api_key": "",
        "google_cse_id": "013611106330597893267:tfgl3wxdtbp",
    }

    # Option descriptions
    optdescs = {
        "count": "Bing 搜索引擎结果数量.",
        "method": "要使用的搜索引擎：'Google' 或 'Bing'.",
        "tighten": "通过期望找到社交媒体个人资料页面结果中提到的目标域名的关键字来搜索结果?",
        "bing_api_key": "Bing API 密钥用于搜索社交媒体的个人资料.",
        "google_api_key": "Google API 密钥用于搜索社交媒体的个人资料.",
        "google_cse_id": "Google 自定义搜索引擎 ID.",
    }

    keywords = None
    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()
        self.keywords = None
        self.errorState = False

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    def watchedEvents(self):
        return ["HUMAN_NAME"]

    # What events this module produces
    # This is to support the end user in selecting modules based on events
    # produced.
    def producedEvents(self):
        return ["SOCIAL_MEDIA", "RAW_RIR_DATA"]

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data
        self.currentEventSrc = event

        if self.errorState:
            return

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if self.opts['google_api_key'] == "" and self.opts['bing_api_key'] == "":
            self.error("You enabled GO_socialprofiles but did not set a Google or Bing API key!")
            self.errorState = True
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        if self.keywords is None:
            self.keywords = self.GhostOsint.domainKeywords(
                self.getTarget().getNames(), self.opts["_internettlds"]
            )
            if len(self.keywords) == 0:
                self.keywords = None

        for site in sites:
            s = str(sites[site][0]).format(name=eventData)
            searchStr = s.replace(" ", "%20")
            res = None

            if self.opts["method"].lower() == "yahoo":
                self.error(
                    "Yahoo is no longer supported. Please try 'bing' or 'google'."
                )
                return

            if self.opts["method"].lower() == "google":
                res = self.GhostOsint.googleIterate(
                    searchString=searchStr,
                    opts={
                        "timeout": self.opts["_fetchtimeout"],
                        "useragent": self.opts["_useragent"],
                        "api_key": self.opts["google_api_key"],
                        "cse_id": self.opts["google_cse_id"],
                    },
                )
                self.__dataSource__ = "Google"

            if self.opts["method"].lower() == "bing":
                res = self.GhostOsint.bingIterate(
                    searchString=searchStr,
                    opts={
                        "timeout": self.opts["_fetchtimeout"],
                        "useragent": self.opts["_useragent"],
                        "count": self.opts["count"],
                        "api_key": self.opts["bing_api_key"],
                    },
                )
                self.__dataSource__ = "Bing"

            if res is None:
                self.info("No data returned from " + self.opts["method"] + ".")
                continue

            if self.checkForStop():
                return

            # Submit the results for analysis
            evt = GhostOsintEvent(
                "RAW_RIR_DATA", str(res), self.__name__, event
            )
            self.notifyListeners(evt)

            instances = list()
            for searchDom in sites[site][1]:
                # Search both the urls & the search engine web content
                search_string = " ".join(res["urls"] + [str(res)])

                matches = re.findall(
                    searchDom, search_string, re.IGNORECASE | re.MULTILINE
                )

                if not matches:
                    continue

                for match in matches:
                    self.debug("Match found: " + match)
                    if match in instances:
                        continue
                    else:
                        instances.append(match)

                    if self.checkForStop():
                        return

                    # Fetch the profile page if we are checking
                    # for a firm relationship.
                    # Keywords might be empty if the target was an IP, subnet or name.
                    if self.opts["tighten"] and self.keywords:
                        match = urllib.parse.unquote(match)
                        self.debug(
                            "Tightening results to look for " + str(self.keywords)
                        )
                        pres = self.GhostOsint.fetchUrl(
                            match,
                            timeout=self.opts["_fetchtimeout"],
                            useragent=self.opts["_useragent"],
                            verify=False
                        )

                        if pres["content"] is None:
                            continue
                        else:
                            found = False
                            for kw in self.keywords:
                                if re.search(
                                    r"[^a-zA-Z\-\_]" + kw + r"[^a-zA-Z\-\_]",
                                    pres["content"],
                                    re.IGNORECASE,
                                ):
                                    found = True
                            if not found:
                                continue

                    self.info("Social Media Profile found at " + site + ": " + match)
                    match = urllib.parse.unquote(match)
                    evt = GhostOsintEvent(
                        "SOCIAL_MEDIA", site + ": <SFURL>" + match + "</SFURL>", self.__name__, event
                    )
                    self.notifyListeners(evt)


# End of GO_socialprofiles class
