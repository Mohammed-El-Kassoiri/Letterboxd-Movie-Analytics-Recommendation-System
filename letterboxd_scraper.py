import requests
from bs4 import BeautifulSoup
import csv
import time
import re
from urllib.parse import urljoin
from datetime import datetime

class LetterboxdScraper:
    def __init__(self, username):
        self.username = username
        self.base_url = "https://letterboxd.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.movies_data = []
    
    def get_page(self, url):
        """Generic method to get any page"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def get_num_pages(self, section='films'):
        """Get total number of pages for a section"""
        if section == 'likes/films':
            url = f"{self.base_url}/{self.username}/likes/films/"
        else:
            url = f"{self.base_url}/{self.username}/{section}/"
        
        soup = self.get_page(url)
        if not soup:
            return 1
        
        # Find pagination
        pagination = soup.find('div', class_='pagination')
        if pagination:
            page_links = pagination.find_all('li', class_='paginate-page')
            if page_links:
                try:
                    return int(page_links[-1].text.strip())
                except:
                    return 1
        return 1
    
    def get_movie_details(self, movie_url):
        """Scrape detailed information from a movie page"""
        try:
            soup = self.get_page(movie_url)
            if not soup:
                return None
            
            details = {}
            
            # Movie name from h1
            title_elem = soup.find('h1', class_='headline-1')
            if title_elem:
                details['movie_name'] = title_elem.get_text(strip=True).replace('\xa0', ' ')
            else:
                details['movie_name'] = 'N/A'
            
            # Year
            year_elem = soup.find('small', class_='number')
            details['year'] = year_elem.text.strip() if year_elem else 'N/A'
            
            # Genres
            genre_links = soup.find_all('a', href=re.compile(r'/films/genre/'))
            details['genres'] = ', '.join([g.text.strip() for g in genre_links]) if genre_links else 'N/A'
            
            ## Description
            #desc_elem = soup.find('div', class_='truncate')
            #if desc_elem:
            #    desc_p = desc_elem.find('p')
            #    details['description'] = desc_p.text.strip() if desc_p else 'N/A'
            #else:
            #    details['description'] = 'N/A'
            #
            # Rating statistics - weighted average
            rating_meta = soup.find('meta', attrs={'name': 'twitter:data2'})
            if rating_meta:
                content = rating_meta.get('content', '')
                rating_match = re.search(r'([\d.]+)\s+out of', content)
                details['vote_average'] = rating_match.group(1) if rating_match else 'N/A'
            else:
                details['vote_average'] = 'N/A'
            
            # Vote count from histogram link
            histogram_link = soup.find('a', href=re.compile(r'rating-histogram'))
            if histogram_link:
                count_text = histogram_link.get_text(strip=True)
                count_match = re.search(r'([\d,]+)', count_text)
                details['vote_count'] = count_match.group(1).replace(',', '') if count_match else 'N/A'
            else:
                details['vote_count'] = 'N/A'
            
            # Popularity - number of fans
            fans_link = soup.find('a', class_='has-icon', href=re.compile(r'/fans/'))
            if fans_link:
                fans_text = fans_link.get_text(strip=True)
                fans_match = re.search(r'([\d,]+)', fans_text)
                details['popularity'] = fans_match.group(1).replace(',', '') if fans_match else '0'
            else:
                details['popularity'] = '0'
            
            return details
            
        except Exception as e:
            print(f"Error getting movie details: {e}")
            return None
    
    def extract_user_rating(self, poster_div):
        """Extract user's rating from the poster's parent link"""
        # Look for rating in the parent link structure
        parent = poster_div.find_parent('li')
        if parent:
            rating_span = parent.find('span', class_=re.compile(r'rated-'))
            if rating_span:
                classes = rating_span.get('class', [])
                for cls in classes:
                    if cls.startswith('rated-'):
                        try:
                            rating_value = int(cls.split('-')[1])
                            return str(rating_value / 2.0)
                        except:
                            pass
        return 'Not Rated'
    
    def scrape_section(self, section='films', max_pages=None):
        """
        Scrape movies from different sections
        Sections: 'films', 'reviews', 'diary', 'watchlist', 'likes/films'
        """
        print(f"\n{'='*60}")
        print(f"Scraping {section} for user: {self.username}")
        print(f"{'='*60}\n")
        
        # Get total pages
        total_pages = self.get_num_pages(section)
        print(f"Total pages found: {total_pages}")
        
        if max_pages:
            total_pages = min(total_pages, max_pages)
        
        movies_found = 0
        
        for page in range(1, total_pages + 1):
            # Build URL based on section
            if section == 'likes/films':
                url = f"{self.base_url}/{self.username}/likes/films/page/{page}/"
            else:
                url = f"{self.base_url}/{self.username}/{section}/page/{page}/"
            
            print(f"Page {page}/{total_pages}: {url}")
            soup = self.get_page(url)
            
            if not soup:
                continue
            
            # Find all movie items - they're in div.react-component with data-target-link
            movie_items = soup.find_all('div', class_='react-component', attrs={'data-target-link': True})
            
            if not movie_items:
                print(f"  No movies found on this page")
                continue
            
            print(f"  Found {len(movie_items)} movies on this page")
            
            for item in movie_items:
                # Get movie slug from data-target-link
                target_link = item.get('data-target-link', '')
                
                if not target_link or '/film/' not in target_link:
                    continue
                
                # Extract slug from /film/slug-name/
                movie_slug = target_link.strip('/').split('/')[-1]
                
                # Get movie name from data attribute
                movie_name_preview = item.get('data-item-name', movie_slug)
                
                # Check if already scraped
                if any(m['movie_id'] == movie_slug for m in self.movies_data):
                    print(f"    ↺ Skipping duplicate: {movie_slug}")
                    continue
                
                movie_url = f"{self.base_url}/film/{movie_slug}/"
                
                # Get user's rating
                user_rating = self.extract_user_rating(item)
                
                print(f"    → Fetching: {movie_name_preview}")
                
                # Get detailed movie information
                movie_details = self.get_movie_details(movie_url)
                
                if movie_details:
                    movie_data = {
                        'movie_id': movie_slug,
                        'username': self.username,
                        'movie_name': movie_details['movie_name'],
                        'year': movie_details['year'],
                        'genres': movie_details['genres'],
                        'rating': user_rating,
                        #'description': movie_details['description'],
                        'popularity': movie_details['popularity'],
                        'vote_average': movie_details['vote_average'],
                        'vote_count': movie_details['vote_count'],
                        #'source_section': section
                    }
                    
                    self.movies_data.append(movie_data)
                    movies_found += 1
                    print(f"      ✓ Saved: {movie_details['movie_name']} ({movie_details['year']})")
                
                # Rate limiting
                time.sleep(1.5)
            
            # Longer delay between pages
            if page < total_pages:
                print(f"  Waiting before next page...")
                time.sleep(2)
        
        print(f"\n✓ Movies found in {section}: {movies_found}")
        print(f"✓ Total unique movies: {len(self.movies_data)}\n")
        
        return self.movies_data
    
    def scrape_all_sections(self, sections=None, max_pages_per_section=None):
        """
        Scrape multiple sections
        Default sections: films, reviews, diary, watchlist, likes/films
        """
        if sections is None:
            sections = ['films', 'reviews', 'diary', 'watchlist', 'likes/films']
        
        print(f"\n🎬 LETTERBOXD SCRAPER")
        print(f"{'='*60}")
        print(f"User: {self.username}")
        print(f"Sections: {', '.join(sections)}")
        print(f"{'='*60}\n")
        
        for section in sections:
            try:
                self.scrape_section(section, max_pages=max_pages_per_section)
            except KeyboardInterrupt:
                print("\n\n⚠️  Scraping interrupted by user")
                break
            except Exception as e:
                print(f"❌ Error scraping {section}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'='*60}")
        print(f"✅ SCRAPING COMPLETE")
        print(f"Total unique movies: {len(self.movies_data)}")
        print(f"{'='*60}\n")
        
        return self.movies_data
    
    def save_to_csv(self, filename=None):
        """Save scraped data to CSV file"""
        if not self.movies_data:
            print("❌ No data to save!")
            return
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.username}_letterboxd_{timestamp}.csv"
        
        fieldnames = [
            'movie_id', 'username', 'movie_name', 'year', 'genres', 
            'rating', 
            #'description', 
            'popularity', 'vote_average', 
            'vote_count'
            #, 'source_section'
        ]
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.movies_data)
            
            print(f"✅ Data saved to: {filename}")
            print(f"📊 Total records: {len(self.movies_data)}\n")
            return filename
        except Exception as e:
            print(f"❌ Error saving CSV: {e}")
            return None


# Usage examples
if __name__ == "__main__":
    
    # QUICK TEST - Scrape just 2 pages of films
    print("=" * 70)
    print("QUICK TEST: Scraping 2 pages of films")
    print("=" * 70)
    scraper = LetterboxdScraper("marwanmovies")
    scraper.scrape_section('films', max_pages=2)
    if scraper.movies_data:
        scraper.save_to_csv("test_output.csv")
    
    # Uncomment below for full scraping
    
    # # FULL SCRAPE - All sections
    # print("\n" + "=" * 70)
    # print("FULL SCRAPE: All sections")
    # print("=" * 70)
    # scraper = LetterboxdScraper("marwanmovies")
    # scraper.scrape_all_sections()
    # scraper.save_to_csv()
    
    # # SPECIFIC SECTIONS
    # scraper2 = LetterboxdScraper("marwanmovies")
    # scraper2.scrape_all_sections(sections=['films', 'watchlist'])
    # scraper2.save_to_csv()