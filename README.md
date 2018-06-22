# web_scraper

This script downloads a web page and scrape data. The data to scrape are specified by list of xpath. In which, each xpath corresponds
to a column. Thus, the scripts creates a table that can be save to cvs file.

The script can select a random user agent from a file and cycle proxy from free proxy list and/or from a proxy list.

## Usage

```
usage: web_scraper.py [-h] (-u URL | -f FILE) [--proxy-file FILE] [-p]
                      [-s FILE] [-a FILE] [-d FROM-TO]
                      (-x XPATHS [XPATHS ...] | --xpath-file FILE) [-o FILE]

optional arguments:
  -h, --help            show this help message and exit
  -u URL, --url URL     scrape web page from url
  -f FILE, --file FILE  scrape web page from file
  --proxy-file FILE     rotate proxies from proxy file
  -p, --proxy           rotate proxies from https://free-proxy-list.net/
  -s FILE, --save-file FILE
                        save web page
  -a FILE, --user-agent-file FILE
                        randomize user agents from list file
  -d FROM-TO, --delay-range FROM-TO
                        randomize download delay (second) from this range
  -x XPATHS [XPATHS ...], --xpaths XPATHS [XPATHS ...]
                        xpaths for the columns
  --xpath-file FILE     file containing the xpaths for the columns
  -o FILE, --output-file FILE
                        save scrape data to csv file
```
             
## Requirements

    python 3.5+
    requests
    lxml

## Example run

Download web page and scrape for 2 xpaths and print csv output on console:
```
python3 web_scraper.py -x //span[@class='text'] //small[@class='author'] -u http://quotes.toscrape.com/
```

Download web page with online free proxy and user agent plus delay of 2 to 5 seconds then save the downloaded page to quotes.html and csv output to quotes.csv 
```
python3 web_scraper.py -x //span[@class='text'] //small[@class='author'] -u http://quotes.toscrape.com/ -p -a user_agents.txt -d 2-5 -s quotes.html -o quotes.csv
```

Scrape data from local file quotes.html and save the scraped data to quotes csv.
```
python3 web_scraper.py -x //span[@class='text'] //small[@class='author'] -f quotes.html -o quotes.csv
```
