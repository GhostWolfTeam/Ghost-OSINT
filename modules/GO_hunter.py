# -------------------------------------------------------------------------------
# Name:         GO_hunter
# Purpose:      Query hunter.io using their API.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     22/02/2017
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import urllib.error
import urllib.parse
import urllib.request

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_hunter(GhostOsintPlugin):

    meta = {
        'name': "Hunter.io",
        'summary': "检查 hunter.io 上的电子邮件地址和姓名.",
        'flags': ["apikey"],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Search Engines"],
        'dataSource': {
            'website': "https://hunter.io/",
            'model': "FREE_AUTH_LIMITED",
            'references': [
                "https://hunter.io/api"
            ],
            'apiKeyInstructions': [
                "访问 https://hunter.io/",
                "注册一个免费账户",
                "点击 'Account Settings'",
                "点击 'API'",
                "API 密钥将在 'Your API Key'"
            ],
            'favIcon': "https://hunter.io/assets/head/favicon-d5796c45076e78aa5cf22dd53c5a4a54155062224bac758a412f3a849f38690b.ico",
            'logo': "https://hunter.io/assets/head/touch-icon-iphone-fd9330e31552eeaa12b177489943de997551bfd991c4c44e8c3d572e78aea5f3.png",
            'description': "Hunter 可以让你在几秒钟内找到电子邮件地址，并与对你的业务有重要影响的人联系.\n"
            "搜索域名会列出在一家公司工作的所有人员，他们的姓名和电子邮件地址都在网上找到. 它拥有1亿多个电子邮件地址索引、有效的搜索过滤器和评分"
            "，是有史以来最强大的电子邮件查找工具.",
        }
    }

    # Default options
    opts = {
        "api_key": ""
    }

    # Option descriptions
    optdescs = {
        "api_key": "Hunter.io API 密钥."
    }

    # Be sure to completely clear any class variables in setup()
    # or you run the risk of data persisting between scan runs.

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()
        self.errorState = False

        # Clear / reset any other class member variables here
        # or you risk them persisting between threads.

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    def watchedEvents(self):
        return ["DOMAIN_NAME", "INTERNET_NAME"]

    # What events this module produces
    def producedEvents(self):
        return ["EMAILADDR", "EMAILADDR_GENERIC", "RAW_RIR_DATA"]

    def query(self, qry, offset=0, limit=10):
        params = {
            "domain": qry.encode('raw_unicode_escape').decode("ascii", errors='replace'),
            "api_key": self.opts['api_key'],
            "offset": str(offset),
            "limit": str(limit)
        }

        url = f"https://api.hunter.io/v2/domain-search?{urllib.parse.urlencode(params)}"

        res = self.GhostOsint.fetchUrl(url, timeout=self.opts['_fetchtimeout'], useragent="GhostOSINT")

        if res['code'] == "404":
            return None

        if not res['content']:
            return None

        try:
            return json.loads(res['content'])
        except Exception as e:
            self.error(f"Error processing JSON response from hunter.io: {e}")

        return None

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if self.errorState:
            return

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        if self.opts['api_key'] == "":
            self.error("You enabled GO_hunter but did not set an API key!")
            self.errorState = True
            return

        data = self.query(eventData, 0, 10)
        if not data:
            return

        if "data" not in data:
            return

        # Check if we have more results on further pages
        if "meta" in data:
            maxgoal = data['meta'].get('results', 10)
        else:
            maxgoal = 10

        rescount = len(data['data'].get('emails', list()))

        while rescount <= maxgoal:
            for email in data['data'].get('emails', list()):
                # Notify other modules of what you've found
                em = email.get('value')
                if not em:
                    continue
                if em.split("@")[0] in self.opts['_genericusers'].split(","):
                    evttype = "EMAILADDR_GENERIC"
                else:
                    evttype = "EMAILADDR"

                e = GhostOsintEvent(evttype, em, self.__name__, event)
                self.notifyListeners(e)

                if 'first_name' in email and 'last_name' in email:
                    if email['first_name'] is not None and email['last_name'] is not None:
                        n = email['first_name'] + " " + email['last_name']
                        e = GhostOsintEvent("RAW_RIR_DATA", "Possible full name: " + n,
                                            self.__name__, event)
                        self.notifyListeners(e)

            if rescount >= maxgoal:
                return

            data = self.query(eventData, rescount, 10)
            if data is None:
                return
            if "data" not in data:
                return

            rescount += len(data['data'].get('emails', list()))

# End of GO_hunter class
