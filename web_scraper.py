import argparse
import os
import sys
import time
import requests
import random
import logging
import csv
from itertools import cycle
from lxml import etree
from urllib.request import url2pathname
from urllib.parse import urljoin, urlparse
from abc import ABC, abstractmethod

FREE_PROXY_LIST_NET_URL = 'https://free-proxy-list.net/'


class Loader(ABC):

    @abstractmethod
    def get_content(self, location):
        pass


class Downloader(Loader):

    def __init__(self, user_agent_pool, proxy_pool, delayer):
        self.user_agent_pool = user_agent_pool
        self.proxy_pool = proxy_pool
        self.delayer = delayer

    def get_content(self, location):
        if '://' not in location:
            location = 'http://' + location

        max_retry = 5
        for request_count in range(1, max_retry + 1):
            try:
                self.delayer.sleep()

                logging.debug('Downloading %s ...', location)

                headers = None
                if self.user_agent_pool:
                    user_agent = self.user_agent_pool.get_user_agent()
                    logging.debug('User agent: %s', user_agent)
                    headers = {'User-Agent': user_agent}

                proxies = None
                if self.proxy_pool:
                    proxy = self.proxy_pool.get_proxy()
                    logging.debug('Proxy: %s', proxy)
                    proxies = {'http': proxy, 'https': proxy}

                response = requests.get(location, headers=headers, proxies=proxies)
                content = response.text
                if is_captcha(content):
                    raise Exception('Got captcha page')
                return content

            except Exception as e:
                logging.warning(str(e))
                logging.debug('Retry left: %d', max_retry - request_count)

        raise Exception('Cannot download from ' + location)


class FileLoader(Loader):

    def __init__(self, save_dir):
        self.save_dir = save_dir

    def get_content(self, location):
        load_file_path = location

        # look for the end '/' of url and append index.html
        if load_file_path.endswith('/'):
            load_file_path += 'index.html'

        # remove the start '/' of url
        if load_file_path.startswith('/'):
            load_file_path = load_file_path[1:]

        load_file_path = os.path.join(self.save_dir, load_file_path)

        with open(load_file_path, 'r', encoding='utf-8') as f:
            return f.read()


class RandomizeUserAgents:

    def __init__(self, ua_file=None, ua_list=None):
        self.user_agents = set()
        if ua_file:
            with open(ua_file, 'r') as f:
                for line in f:
                    self.user_agents.add(line.strip())
        if ua_list:
            self.user_agents |= set(ua_list)

    def get_user_agent(self):
        return random.choice(tuple(self.user_agents))


class CycleProxies:

    def __init__(self, proxy_file=None, proxy_list=None):
        proxies = set()
        if proxy_file:
            with open(proxy_file, 'r') as f:
                for line in f:
                    proxies.add(line.strip())
        if proxy_list:
            proxies |= set(proxy_list)
        self.proxy_cycle = cycle(proxies)

    def get_proxy(self):
        return next(self.proxy_cycle)


class RandomizeSleep:

    def __init__(self, range_from, range_to):
        self.range_from = range_from
        self.range_to = range_to

    def sleep(self):
        delay = random.uniform(float(self.range_from), float(self.range_to))
        logging.debug('Delay: %s s', delay)
        time.sleep(delay)


class Scraper:

    def __init__(self, source, max_page=0, save_dir=''):
        self.source = source
        self.max_page = max_page
        self.save_dir = save_dir
        self.page_num = 0

    def url_to_file_path(self, url):
        url_path = urlparse(url).path
        if url_path.endswith('/'):
            url_path += 'index.html'
        if url_path.startswith('/'):
            url_path = url_path[1:]
        return url2pathname(url_path)

    def scrape(self, url, xml_paths, next_page_xml_path):

        content = self.source.get_content(url)
        if self.save_dir:
            save_file_path = os.path.join(self.save_dir, self.url_to_file_path(url))
            os.makedirs(os.path.dirname(save_file_path), exist_ok=True)
            with open(save_file_path, 'w', encoding='utf-8') as f:
                f.write(content)

        html_parser = etree.HTMLParser()
        root = etree.fromstring(content, parser=html_parser)

        # parse
        table_cols = []
        for xml_path in xml_paths:
            col_values = []
            elements = root.xpath(xml_path)
            for element in elements:
                element_text = get_text_content(element)
                col_values.append(element_text)
            table_cols.append(col_values)

        # transpose cols to rows
        yield from zip(*table_cols)

        if int(self.max_page) == self.page_num + 1:
            return

        self.page_num += 1

        if next_page_xml_path:
            next_page_element = root.xpath(next_page_xml_path)
            if len(next_page_element) > 0 and 'href' in next_page_element[0].attrib:
                next_page_location = urljoin(url, next_page_element[0].attrib.get('href'))
                yield from self.scrape(next_page_location, xml_paths, next_page_xml_path)


def is_captcha(content):
    html_parser = etree.HTMLParser()
    root = etree.fromstring(content, parser=html_parser)
    return root.find('script[@src="https://www.google.com/recaptcha/api.js"]') is not None


def get_proxies_from_free_proxy_list_net():
    # this function can break if the free-proxy-list.net html structure changed

    response = requests.get(FREE_PROXY_LIST_NET_URL)
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.text, parser=html_parser)

    row_ctr = 0
    proxies = set()
    for html_row in root.iterfind('.//tbody/tr'):
        if row_ctr == 50:  # parse up to 50th row
            break

        td_ctr = 0
        td_list = []
        for html_td in html_row.iterfind('td'):
            if td_ctr < 7:  # parse up to 7th row
                td_list.append(html_td.text)
            td_ctr += 1
        if len(td_list) == 7 and td_list[6] == 'yes':  # https
            proxies.add(':'.join(td_list[:2]))
        row_ctr += 1
    return proxies


def get_text_content(element):
    content = ''
    if element.text:
        content += element.text
    for child in element.getchildren():
        if child.text:
            content += child.text
        if child.tail:
            content += child.tail
    if element.tail:
        content += element.tail
    return content.strip()


def print_csv(rows, f):
    writer = csv.writer(f)
    for row in rows:
        writer.writerow(row)


def parse_arg():
    parser = argparse.ArgumentParser()

    web_page_group = parser.add_mutually_exclusive_group(required=True)
    web_page_group.add_argument('-u', '--url',
                                help='scrape web page from url')
    web_page_group.add_argument('-f', '--file',
                                help='scrape web page from file')
    parser.add_argument('--proxy-file',
                        metavar='FILE',
                        help='rotate proxies from proxy file')
    parser.add_argument('-p', '--proxy',
                        action='store_true',
                        help='rotate proxies from ' + FREE_PROXY_LIST_NET_URL)
    parser.add_argument('-s', '--save-dir',
                        metavar='DIR',
                        help='save web pages to this directory')
    parser.add_argument('-a', '--user-agent-file',
                        metavar='FILE',
                        help='randomize user agents from list file')
    parser.add_argument('-d', '--delay-range',
                        default='0.0-0.0',
                        metavar='FROM-TO',
                        help='randomize download delay (second) from this range')
    xpath_group = parser.add_mutually_exclusive_group(required=True)
    xpath_group.add_argument('-x', '--xpaths',
                             nargs='+',
                             help='xpaths for the columns')
    xpath_group.add_argument('--xpath-file',
                             metavar='FILE',
                             help='file containing the xpaths for the columns')
    parser.add_argument('--next-page-xpath',
                        metavar='XPATH',
                        help='xpath containing the href url to next page')
    parser.add_argument('--max-page',
                        default='0',
                        help='scrape (next) pages up to max page (default is to scrape all pages)')
    parser.add_argument('-o', '--output-file',
                        metavar='FILE',
                        help='save scrape data to csv file')

    args = parser.parse_args()
    return args


def main():
    try:
        # setup logging
        logging.basicConfig(filename='web_scraper.log',
                            filemode='w',
                            format='%(levelname)s:%(message)s',
                            level=logging.DEBUG)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        logging.getLogger('').addHandler(console)

        args = parse_arg()

        loader = None
        location = None
        if args.url:
            # prepare randomize user agent
            user_agent_pool = None
            if args.user_agent_file:
                user_agent_pool = RandomizeUserAgents(args.user_agent_file)

            # prepare randomize proxy
            proxy_pool = None
            if args.proxy or args.proxy_file:
                proxy_list = get_proxies_from_free_proxy_list_net() if args.proxy else []
                proxy_pool = CycleProxies(args.proxy_file, proxy_list)

            # prepare randomize delay between downloads
            (delay_from, delay_to) = args.delay_range.split('-', 2)
            delayer = RandomizeSleep(float(delay_from), float(delay_to))

            loader = Downloader(user_agent_pool, proxy_pool, delayer)
            location = args.url
        elif args.file:
            if not os.path.isfile(args.file):
                raise Exception('Cannot find input file: ' + args.file)

            loader = FileLoader(os.path.dirname(args.file))
            location = os.path.basename(args.file)

        # prepare xpath list
        xml_paths = None
        if args.xpath_file:
            with open(args.xpath_file, 'r', encoding='utf-8') as f:
                xml_paths = f.readlines()
        elif args.xpaths:
            xml_paths = args.xpaths

        # scrape pages
        scraper = Scraper(loader, args.max_page, args.save_dir)
        table = scraper.scrape(location, xml_paths, args.next_page_xpath)

        # save/print output
        if args.output_file:
            with open(args.output_file, 'w', newline='', encoding='utf-8') as f:
                print_csv(table, f)
        else:
            print_csv(table, sys.stdout)

    except Exception as e:
        logging.error(str(e))
        exit(1)


if __name__ == "__main__":
    main()
