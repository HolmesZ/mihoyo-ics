from datetime import datetime, timedelta
import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from icalendar import Calendar, Event
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# 常量配置
BASE_URL = 'https://www.miyoushe.com/zzz/search'
API_BASE_URL = 'https://bbs-api.miyoushe.com/painter/wapi/searchPosts'
VERSION_FILE = 'version.json'
ICS_FILE = 'zzz_events.ics'
WAIT_TIMEOUT = 10

# 正则表达式模式
AGENTS_PATTERN = r'\[(.*?)\((.*?)\)\]'
TIME_PATTERN = r'(\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2})\s*~\s*(\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2})'
VERSION_PATTERN = r'(\d+\.\d+)版本更新后\s*~\s*(\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2})'

# 配置日志记录器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('mihoyo-ics')


class PostCrawler:
    """帖子爬取器，负责获取和解析帖子内容"""

    def __init__(self):
        self.driver = self._init_webdriver()
        self.wait = WebDriverWait(self.driver, WAIT_TIMEOUT)

    def _init_webdriver(self) -> webdriver.Chrome:
        """初始化WebDriver"""
        try:
            chrome_options = Options()
            options = [
                "--headless",
                "--disable-gpu",
                "--window-size=1920,1200",
                "--ignore-certificate-errors",
                "--disable-extensions",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
            for option in options:
                chrome_options.add_argument(option)
            return webdriver.Chrome(
                service=Service(ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install()),
                options=chrome_options
            )
        except Exception as e:
            logger.error(f'初始化WebDriver失败: {str(e)}', exc_info=True)
            raise

    def __del__(self):
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f'关闭WebDriver失败: {str(e)}', exc_info=True)

    def get_posts(self, keyword: str) -> List[Dict[str, str]]:
        """获取调频说明帖子列表"""
        try:
            logger.info(f'开始获取关键词为 "{keyword}" 的帖子列表')
            self.driver.get(f'{BASE_URL}?keyword={keyword}')
            
            self.wait.until(EC.presence_of_all_elements_located(
                (By.CLASS_NAME, 'mhy-article-card')
            ))
            
            posts = []
            article_list = self.driver.find_elements(By.CLASS_NAME, 'mhy-article-card')
            
            for article in article_list:
                try:
                    title_element = article.find_element(By.CLASS_NAME, 'mhy-article-card__title')
                    link_element = article.find_element(By.CLASS_NAME, 'mhy-article-card__link')
                    
                    if title_element and link_element:
                        posts.append({
                            'title': title_element.text.strip(),
                            'url': link_element.get_attribute('href')
                        })
                except Exception as e:
                    logger.warning(f'解析帖子元素失败: {str(e)}', exc_info=True)
                    continue
            
            logger.info(f'成功获取到 {len(posts)} 个帖子')
            return posts
        except Exception as e:
            logger.error(f'获取帖子列表失败: {str(e)}', exc_info=True)
            return []

    def parse_post_content(self, post_url: str) -> Optional[Dict]:
        """解析单个帖子内容，提取活动时间和描述"""
        try:
            logger.info(f'开始解析帖子内容: {post_url}')
            self.driver.get(post_url)
            
            self.wait.until(EC.presence_of_element_located(
                (By.CLASS_NAME, 'mhy-article-page__content')
            ))
            
            title = self._get_element_text(By.CLASS_NAME, 'mhy-article-page__title')
            description = self._get_element_text(By.CLASS_NAME, 'mhy-article-page__content')
            
            if not description:
                logger.warning('帖子内容为空')
                return None

            if not self._is_valid_post_content(title, description):
                return None
            
            title = self._extract_agents_title(description) or title
            event_time = self._extract_event_time(description)
            
            if event_time:
                return {
                    'title': title,
                    'start_time': event_time[0],
                    'end_time': event_time[1],
                    'description': ''
                }
            
            logger.warning(f'帖子 "{title}" 中未找到有效的时间信息')
            return None
        except Exception as e:
            logger.error(f'解析帖子内容失败: {str(e)}', exc_info=True)
            return None

    def _get_element_text(self, by: str, value: str) -> str:
        """获取元素文本内容"""
        try:
            element = self.driver.find_element(by=by, value=value)
            return element.text.strip() if element else ''
        except Exception:
            return ''

    def _is_valid_post_content(self, title: str, description: str) -> bool:
        """检查帖子内容是否有效"""
        if "音擎" in description:
            logger.info(f'帖子 "{title}" 包含音擎关键词，跳过处理')
            return False

        if "代理人" not in description:
            logger.info(f'帖子 "{title}" 不包含代理人关键词，跳过处理')
            return False

        return True

    def _extract_agents_title(self, description: str) -> Optional[str]:
        """从描述中提取代理人信息作为标题"""
        agents_matches = re.findall(AGENTS_PATTERN, description)
        if agents_matches:
            unique_agents = list(dict.fromkeys(f"{match[0]}({match[1]})" for match in agents_matches))
            title = '、'.join(unique_agents)
            logger.info(f'从帖子中提取到代理人信息作为标题: {title}')
            return title
        return None

    def _extract_event_time(self, description: str) -> Optional[Tuple[datetime, datetime]]:
        """从描述中提取活动时间"""
        # 尝试匹配直接时间格式
        time_match = re.search(TIME_PATTERN, description)
        if time_match:
            return self._parse_direct_time(time_match)

        # 尝试匹配版本更新格式
        version_match = re.search(VERSION_PATTERN, description)
        if version_match:
            return self._parse_version_time(version_match)

        return None

    def _parse_direct_time(self, time_match: re.Match) -> Tuple[datetime, datetime]:
        """解析直接时间格式"""
        start_time = datetime.strptime(time_match.group(1), '%Y/%m/%d %H:%M:%S')
        end_time = datetime.strptime(time_match.group(2), '%Y/%m/%d %H:%M:%S')
        logger.info(f'找到直接时间格式：开始时间 {start_time}, 结束时间 {end_time}')
        return start_time, end_time

    def _parse_version_time(self, version_match: re.Match) -> Optional[Tuple[datetime, datetime]]:
        """解析版本更新时间格式"""
        version = version_match.group(1)
        end_time = datetime.strptime(version_match.group(2), '%Y/%m/%d %H:%M:%S')
        
        try:
            start_time = self._get_version_start_time(version)
            if start_time:
                logger.info(f'找到版本时间格式：版本 {version}, 开始时间 {start_time}, 结束时间 {end_time}')
                return start_time, end_time
        except Exception as e:
            logger.error(f'解析版本时间失败: {str(e)}', exc_info=True)
        
        return None

    def _get_version_start_time(self, version: str) -> Optional[datetime]:
        """获取版本更新开始时间"""
        try:
            version_data = self._load_version_data()
            if version in version_data:
                return datetime.fromisoformat(version_data[version])

            start_time = self._fetch_version_start_time(version)
            if start_time:
                self._save_version_data(version, start_time, version_data)
                return start_time

        except Exception as e:
            logger.error(f'获取版本开始时间失败: {str(e)}', exc_info=True)
        
        return None

    def _load_version_data(self) -> Dict:
        """加载版本数据"""
        try:
            with open(VERSION_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f'读取版本文件失败: {str(e)}', exc_info=True)
            return {}

    def _fetch_version_start_time(self, version: str) -> Optional[datetime]:
        """从API获取版本更新时间"""
        try:
            logger.info(f'尝试从API获取版本 {version} 的时间')
            api_url = f'{API_BASE_URL}?keyword=【绝区零绳网情报站】{version}版本&size=1'
            response = requests.get(api_url)
            data = response.json()

            if data['retcode'] == 0 and data['data']['list']:
                post = data['data']['list'][0]['post']
                if f'【绝区零绳网情报站】{version}版本' in post['subject']:
                    return datetime.fromtimestamp(post['created_at'])
        except Exception as e:
            logger.error(f'从API获取版本时间失败: {str(e)}', exc_info=True)
        
        return None

    def _save_version_data(self, version: str, start_time: datetime, version_data: Dict):
        """保存版本数据"""
        try:
            version_data[version] = start_time.isoformat()
            with open(VERSION_FILE, 'w') as f:
                json.dump(version_data, f, indent=4)
            logger.info(f'已更新version.json文件')
        except Exception as e:
            logger.error(f'保存版本数据失败: {str(e)}', exc_info=True)


class ICSGenerator:
    """ICS日历文件生成器"""

    def __init__(self):
        self.calendar = Calendar()
        self.calendar.add('prodid', '-//米哈游绝区零调频活动日历//CN')
        self.calendar.add('version', '2.0')
        self.calendar.add('x-wr-calname', '绝区零调频活动')
        self.calendar.add('x-wr-timezone', 'Asia/Shanghai')
        logger.info('初始化日历生成器')

    def add_event(self, event_data: Dict):
        """添加活动到日历"""
        try:
            start_time = event_data['start_time']
            end_time = event_data['end_time']
            duration = end_time - start_time
            
            # 如果事件持续时间超过24小时，则拆分为两个事件
            if duration.total_seconds() > 24 * 3600:
                # 添加开始事件
                start_event = Event()
                start_event.add('summary', f"{event_data['title']} 开始")
                start_event.add('dtstart', start_time)
                start_event.add('dtend', start_time + timedelta(hours=1))  # 设置1小时的持续时间
                start_event.add('description', event_data['description'])
                start_event.add('tzid', 'Asia/Shanghai')
                self.calendar.add_component(start_event)
                
                # 添加结束事件
                end_event = Event()
                end_event.add('summary', f"{event_data['title']} 结束")
                end_event.add('dtstart', end_time - timedelta(hours=1))  # 从结束时间前1小时开始
                end_event.add('dtend', end_time)
                end_event.add('description', event_data['description'])
                end_event.add('tzid', 'Asia/Shanghai')
                self.calendar.add_component(end_event)
                
                logger.info(f'添加拆分事件到日历: {event_data["title"]} (开始和结束)')
            else:
                # 对于短时间事件，保持原有逻辑
                event = Event()
                event.add('summary', event_data['title'])
                event.add('dtstart', start_time)
                event.add('dtend', end_time)
                event.add('description', event_data['description'])
                event.add('tzid', 'Asia/Shanghai')
                self.calendar.add_component(event)
                logger.info(f'添加活动到日历: {event_data["title"]}')
        except Exception as e:
            logger.error(f'添加活动到日历失败: {str(e)}', exc_info=True)

    def save_ics(self, filename: str):
        """保存ICS文件"""
        try:
            with open(filename, 'wb') as f:
                f.write(self.calendar.to_ical())
            logger.info(f'ICS文件已保存: {filename}')
        except Exception as e:
            logger.error(f'保存ICS文件失败: {str(e)}', exc_info=True)


def merge_events(events: List[Dict]) -> Dict[Tuple[str, str], Dict]:
    """合并相同时间段的事件"""
    events_by_time = {}
    for event in events:
        time_key = (event['start_time'].isoformat(), event['end_time'].isoformat())
        if time_key not in events_by_time:
            events_by_time[time_key] = event
        else:
            existing_titles = events_by_time[time_key]['title'].split('、')
            new_titles = event['title'].split('、')
            all_titles = list(dict.fromkeys(existing_titles + new_titles))
            events_by_time[time_key]['title'] = '、'.join(all_titles)
    return events_by_time


def main():
    """主函数"""
    try:
        logger.info('开始执行程序')
        crawler = PostCrawler()
        ics_generator = ICSGenerator()

        # 获取调频说明帖子
        posts = crawler.get_posts('调频说明')
        if not posts:
            logger.error('未获取到任何帖子')
            return

        # 解析帖子内容并获取事件数据
        events = []
        for post in posts:
            event_data = crawler.parse_post_content(post['url'])
            if event_data:
                events.append(event_data)

        if not events:
            logger.error('未解析到任何有效事件')
            return

        # 合并相同时间段的事件
        merged_events = merge_events(events)

        # 添加事件到日历
        for event_data in merged_events.values():
            ics_generator.add_event(event_data)

        # 保存ICS文件
        ics_generator.save_ics(ICS_FILE)
        logger.info('程序执行完成')

    except Exception as e:
        logger.error(f'程序执行失败: {str(e)}', exc_info=True)


if __name__ == '__main__':
    main()