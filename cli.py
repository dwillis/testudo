#!/usr/bin/env python3
"""Command-line interface for the testudo scraper."""

import sys
import argparse
import subprocess
from testudo import TestudoScraper, ScraperConfig, setup_logging

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="University of Maryland course scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --test                    # Test with AAAS department
  %(prog)s --test CMSC               # Test with CMSC department  
  %(prog)s --department CMSC         # Scrape only CMSC department
  %(prog)s --department CMSC --extract-syllabi  # Scrape CMSC with syllabus extraction
  %(prog)s --term 202508             # Scrape specific term
  %(prog)s --department JOUR --term 202508  # Scrape JOUR for specific term
  %(prog)s --verbose --test JOUR     # Test with debug logging
  %(prog)s --to-sqlite courses.db    # Convert existing JSON to SQLite
  %(prog)s --to-csv courses.csv      # Convert existing JSON to CSV
        """
    )
    
    parser.add_argument(
        '--test', 
        nargs='?', 
        const='AAAS',
        help='Test mode - scrape only specified department (default: AAAS)'
    )
    
    parser.add_argument(
        '--department',
        help='Scrape only the specified department (e.g., CMSC, JOUR, MATH)'
    )
    
    parser.add_argument(
        '--extract-syllabi',
        action='store_true',
        help='Extract syllabus titles using browser automation (slower but includes syllabus data)'
    )
    
    parser.add_argument(
        '--term',
        help='Specific term to scrape (e.g., 202508)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable debug logging'
    )
    
    parser.add_argument(
        '--config-file',
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--data-dir',
        default='data',
        help='Directory to save course data (default: data)'
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between requests in seconds (default: 1.0)'
    )
    
    parser.add_argument(
        '--to-sqlite',
        metavar='DATABASE',
        help='Convert existing JSON files to SQLite database'
    )
    
    parser.add_argument(
        '--to-csv',
        metavar='CSV_FILE',
        help='Convert existing JSON files to CSV format'
    )
    
    parser.add_argument(
        '--pattern',
        default='**/*.json',
        help='Glob pattern for JSON files when using --to-sqlite (default: **/*.json)'
    )
    
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing output files'
    )
    
    args = parser.parse_args()
    
    # Validate mutually exclusive options
    if args.test and args.department:
        print("Error: --test and --department options cannot be used together")
        sys.exit(1)
    
    # Handle SQLite conversion
    if args.to_sqlite:
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_to_sqlite_script = os.path.join(script_dir, 'json_to_sqlite.py')
        
        cmd = [sys.executable, json_to_sqlite_script, args.data_dir, args.to_sqlite]
        
        if args.pattern != '**/*.json':
            cmd.extend(['--pattern', args.pattern])
        
        if args.overwrite:
            cmd.append('--overwrite')
            
        if args.verbose:
            cmd.append('--verbose')
        
        try:
            result = subprocess.run(cmd, check=True)
            sys.exit(result.returncode)
        except subprocess.CalledProcessError as e:
            print(f"Error running SQLite conversion: {e}")
            sys.exit(1)
        except FileNotFoundError:
            print(f"Error: json_to_sqlite.py script not found at {json_to_sqlite_script}")
            sys.exit(1)
    
    # Handle CSV conversion
    if args.to_csv:
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json2csv_script = os.path.join(script_dir, 'json2csv.py')
        
        cmd = [sys.executable, json2csv_script, '--input', args.data_dir, '--output', args.to_csv]
        
        if args.verbose:
            cmd.append('--verbose')
        
        try:
            result = subprocess.run(cmd, check=True)
            sys.exit(result.returncode)
        except subprocess.CalledProcessError as e:
            print(f"Error running CSV conversion: {e}")
            sys.exit(1)
        except FileNotFoundError:
            print(f"Error: json2csv.py script not found at {json2csv_script}")
            sys.exit(1)
    
    # Set up logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)
    
    # Create configuration
    config = ScraperConfig(
        data_dir=args.data_dir,
        request_delay=args.delay,
        log_level=log_level,
        extract_syllabi=args.extract_syllabi
    )
    
    if args.term:
        config.default_term = args.term
    
    # Create and run scraper
    scraper = TestudoScraper(config)
    
    try:
        if args.test:
            scraper.scrape_test(department_id=args.test, term=args.term)
        elif args.department:
            scraper.scrape_department(department_id=args.department, term=args.term)
        else:
            scraper.scrape_full(term=args.term)
    
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        scraper.print_stats()

if __name__ == '__main__':
    main()
