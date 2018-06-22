import argparse
import sys
import time
import requests
import random
import logging
import csv
from itertools import cycle
from lxml import etree

FREE_PROXY_LIST_NET_URL = 'https://free-proxy-list.net/'


class Downloader:
    def __init__(self, user_agent_pool=None, proxy_pool=None, delayer=None):
        self.user_agent_pool = user_agent_pool
        self.proxy_pool = proxy_pool
        self.delayer = delayer

    def download(self, url):
        if '://' not in url:
            url = 'http://' + url

        if self.delayer:
            self.delayer.sleep()

        max_retry = 5
        for request_count in range(1, max_retry + 1):
            try:
                headers = None
                if self.user_agent_pool:
                    headers = {'User-Agent': self.user_agent_pool.get_user_agent()}

                proxies = None
                if self.proxy_pool:
                    proxy = self.proxy_pool.get_proxy()
                    proxies = {'http': proxy, 'https': proxy}

                response = requests.get(url, headers=headers, proxies=proxies)
                content = response.text
                if is_captcha(content):
                    raise Exception('Got captcha page')
                return content

            except Exception as e:
                logging.warning(str(e))
                logging.debug('Retry left: %d', max_retry - request_count)

        raise Exception('Cannot download from ' + url)


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
        user_agent = random.choice(tuple(self.user_agents))
        logging.debug('User agent: %s s', user_agent)
        return user_agent


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
        proxy = next(self.proxy_cycle)
        logging.debug('Proxy: %s', proxy)
        return proxy


class RandomizeSleep:
    def __init__(self, range_from, range_to):
        self.range_from = range_from
        self.range_to = range_to

    def sleep(self):
        delay = random.uniform(float(self.range_from), float(self.range_to))
        logging.debug('Delay: %s s', delay)
        time.sleep(delay)


def is_captcha(content):
    html_parser = etree.HTMLParser()
    root = etree.fromstring(content, parser=html_parser)
    return root.find('script[@src="https://www.google.com/recaptcha/api.js"]') is not None


def get_proxies_from_free_proxy_list_net():
    # this function can break if the free-proxy-list.net html structure changed

    response = requests.get(FREE_PROXY_LIST_NET_URL)
    root = etree.HTML(response.text)

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


def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def read_file_to_lines(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.readlines()


def write_file(content, filepath):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def write_csv_file(rows, csv_file):
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)


def print_csv(rows):
    writer = csv.writer(sys.stdout)
    for row in rows:
        writer.writerow(row)


def download_web_page(args):
    user_agent_pool = None
    if args.user_agent_file:
        user_agent_pool = RandomizeUserAgents(args.user_agent_file)

    proxy_pool = None
    if args.proxy or args.proxy_file:
        proxy_list = get_proxies_from_free_proxy_list_net() if args.proxy else []
        proxy_pool = CycleProxies(args.proxy_file, proxy_list)

    (delay_from, delay_to) = args.delay_range.split('-', 2)
    delayer = RandomizeSleep(float(delay_from), float(delay_to))

    downloader = Downloader(user_agent_pool, proxy_pool, delayer)
    return downloader.download(args.url)


def scrape_web_page(web_content, xml_paths):

    html_parser = etree.HTMLParser()
    root = etree.fromstring(web_content, parser=html_parser)

    # scrape columns
    table_header = []
    table_cols = []
    for xml_path in xml_paths:
        table_header.append(xml_path)

        col_values = []
        elements = root.xpath(xml_path)
        for element in elements:
            element_text = get_text_content(element)
            col_values.append(element_text)
        table_cols.append(col_values)

    # transpose cols to rows
    table_rows = []
    for table_row in zip(*table_cols):
        table_rows.append(table_row)

    table_rows.insert(0, table_header)
    return table_rows


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
    parser.add_argument('-s', '--save-file',
                        metavar='FILE',
                        help='save web page')
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
    parser.add_argument('-o', '--output-file',
                        metavar='FILE',
                        help='save scrape data to csv file')

    args = parser.parse_args()
    return args


def main():
    try:
        logging.basicConfig(filename='web_scraper.log',
                            filemode='w',
                            format='%(levelname)s:%(message)s',
                            level=logging.DEBUG)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        logging.getLogger('').addHandler(console)

        args = parse_arg()
        content = read_file(args.file) if args.file else download_web_page(args)
        if args.save_file:
            write_file(content, args.save_file)
        xml_paths = read_file_to_lines(args.xpath_file) if args.xpath_file else args.xpaths
        table = scrape_web_page(content, xml_paths)
        if args.output_file:
            write_csv_file(table, args.output_file)
        else:
            print_csv(table)

    except Exception as e:
        logging.error(str(e))
        exit(1)


if __name__ == "__main__":
    main()
