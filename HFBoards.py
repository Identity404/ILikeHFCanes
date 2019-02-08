from bs4 import BeautifulSoup
import time
import requests
import logging


class HfBoards:
    BASE = 'https://hfboards.mandatory.com'
    logged_in = False

    def __init__(self, username, password):
        """Creates a HFboards Requests session and logs supplied username in

        Parameters
        ----------
        username : str
            Hfboards username
        password : str
            Hfboards password
        """
        self.hf_session = requests.Session()
        resp = self.hf_session.get(self.BASE)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'}
        payload = {"login": username,
                   "register": "0",
                   "password": password,
                   "remember": "1",
                   "cookie_check": "1",
                   "redirect": "/"}

        resp = self.hf_session.post(self.BASE + '/login/login', data=payload, headers=headers, stream=False)

        self.visited_threads = set()
        if self.__is_good_response(resp):
            # print(requests.utils.dict_from_cookiejar(self.hf_session.cookies))
            soup = BeautifulSoup(resp.content, "html.parser")
            self.logout_url = soup.find('a', {'class': 'LogOut'})['href']
            self.logged_in = True

    def logout(self):
        """Ends current HfBoards session by logging out
        """
        if self.logged_in:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'}

        resp = self.hf_session.get(self.BASE + '/' + self.logout_url, headers=headers)

        self.hf_session.close()

    def __is_good_response(self, resp):
        """
        Determines is the Requests response was valid

        Parameters
        ----------
        resp : Response Object

        Returns
        ----------
        Returns True if the response seems to be HTML, False otherwise.
        """
        content_type = resp.headers['Content-Type'].lower()
        return (resp.status_code in [200]
                and content_type is not None
                and content_type.find('html') > -1)

    def __like_posts(self, xf_token, thread_url, posts):
        """Likes posts within a thread page

        Parameters
        ----------
        xf_token : str
            xenforo token hidden in page
        thread_url : str
            url of the thread to like
        posts : bs4.element.Tag
            Beautiful Soup Tags containing urls of post to like on a page
        """
        if self.logged_in:

            cookies = requests.utils.dict_from_cookiejar(self.hf_session.cookies)

            cookie_header = ''

            for key, value in cookies.items():
                cookie_header += "=".join([key, value]) + ';'

            headers = {
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36',
                'cookie': cookie_header,
                'dnt': '1',
                'origin': 'https://hfboards.mandatory.com',
                'referer': thread_url,
                'x-ajax-referer': thread_url,
                'x-requested-with': 'XMLHttpRequest',
            }

            payload = {"_xfNoRedirect": '1',
                       "_xfToken": xf_token,
                       "_xfResponseType": 'json',
                       "_xfRequestUri": thread_url,
                       }

            for count, like in enumerate(posts):
                url = self.BASE + '/' + like['href']
                logger.info("Liking post: " + url)
                resp = self.hf_session.post(url=url, data=payload, headers=headers)
                time.sleep(2)

    def like_thread(self, thread_id, live):
        """Iterates over pages in a thread and gathers all posts to like.
            calls __like_posts for each thread page
        Parameters
        ----------
        thread_id : str
            ex. threads/chad-larose.1474771/
        live : bool
            Is this a live thread? [True/False]
        """
        if self.logged_in:
            # threads are in the form https://hfboards.mandatory.com/threads/thread-id
            url = '/'.join([self.BASE, thread_id])
            resp = self.hf_session.get(url)

            if self.__is_good_response(resp):

                soup = BeautifulSoup(resp.content, "html.parser")

                nav = soup.find('div', {'class': 'PageNav'})

                xf_token = soup.find(name='input', attrs={'name': '_xfToken'})['value']

                posts = soup.find_all('a', {'class': 'LikeLink item control like'})

                logger.info('Liking Page: ' + url)
                self.__like_posts(xf_token, url, posts)

                try:
                    if nav is not None:
                        thread_pages = int(nav['data-last'])
                        curr_page = int(nav['data-page'])

                        if curr_page and curr_page != thread_pages:
                            url_lst = url.split('/')

                            if url_lst[-1] == 'unread':
                                url = '/'.join(url_lst[:-1])

                            for pg_num in range(curr_page + 1, thread_pages + 1):
                                time.sleep(2)

                                if live:
                                    page_url = url + '?page=' + str(pg_num)
                                else:
                                    page_url = url + '/page-' + str(pg_num)

                                resp = self.hf_session.get(page_url)

                                soup = BeautifulSoup(resp.content, "html.parser")

                                logger.info("Liking Page: " + page_url)

                                xf_token = soup.find(name='input', attrs={'name': '_xfToken'})['value']

                                posts = soup.find_all('a', {'class': 'LikeLink item control like'})

                                self.__like_posts(xf_token, page_url, posts)

                except KeyError:
                    pass  # sometimes a nav won't exist or be completely populated, ok to ignore... ie keyerror data-last

    def like_forum(self, forum, num_threads):
        """ Likes all posts in num_threads of most recently posted threads (excluding stickied)

        Parameters
        ----------
        fourm : str
            HfBoards Fourm Id
            ex: carolina-hurricanes.26
        num_threads : int
            Number of threads to like within forum
        """
        if self.logged_in:

            resp = self.hf_session.get(self.BASE + '/forums/' + forum)

            if self.__is_good_response(resp):
                soup = BeautifulSoup(resp.content, "html.parser")

                threads = soup.find_all('a', {'class': 'PreviewTooltip'})

                # only want threads that aren't stickied
                threads = [item['href'] for item in threads if not item.find_parents("li", class_='sticky')]

                for thread in threads[:num_threads]:

                    # We want to make sure we have looped through each thread page once before checking for new posts
                    # strip off /unread from the url and only add it back once it is a part of our set.
                    if thread[-1] == '/':
                        thread = thread[:-1]
                    if thread[-6:] == 'unread':
                        thread = thread[:-7]

                    if thread in self.visited_threads:
                        thread = thread + '/unread'
                    else:
                        self.visited_threads.add(thread)

                    if thread[-4:] == 'live':
                        self.like_thread(thread, True)
                    else:
                        self.like_thread(thread, False)

                    time.sleep(10)

if __name__ == "__main__":

    logging.basicConfig(filename='ilikeyou.log', format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                        level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    conn = HfBoards('username', 'password')

    while True:
        logger.info('liking some threads...')
        conn.like_forum('carolina-hurricanes.26', 5)
        logger.info('going to sleep for a bit...')
        time.sleep(240)


    # like a specific thread
    # conn.like_thread('threads/gdt-edmonton-carolina-6-19-stanley-cup-finals-game-7.260815', False)

    conn.logout()
