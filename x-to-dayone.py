#!/usr/bin/env python3

import argparse
from pathlib import Path
from convert import TwitterToDayOne
import sys
from rich.console import Console
from rich.progress import Progress
from datetime import datetime

console = Console()

def validate_archive(path: Path) -> bool:
    """Validate that the path contains a Twitter archive"""
    if not path.exists():
        console.print(f"[red]Error:[/red] Path {path} does not exist")
        return False
    
    tweets_js = path / 'data' / 'tweets.js'
    if not tweets_js.exists():
        console.print(f"[red]Error:[/red] Could not find tweets.js in {path}/data/")
        return False
    
    media_dir = path / 'data' / 'tweets_media'
    if not media_dir.exists():
        console.print(f"[yellow]Warning:[/yellow] No tweets_media directory found at {media_dir}")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Convert Twitter/X archive to DayOne journal format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -i ~/Downloads/twitter-archive
  %(prog)s -i ./twitter-2024 -o my-journal.zip
  
Note: Your Twitter archive should contain:
  - data/tweets.js
  - data/tweets_media/ (for photos and videos)
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        required=True,
        type=Path,
        help='Path to your Twitter archive directory'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output path for DayOne journal zip (default: twitter_journal_YYYY-MM-DD.zip)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Show detailed error messages'
    )

    args = parser.parse_args()

    # Set default output name if not specified
    if not args.output:
        date_str = datetime.now().strftime('%Y-%m-%d')
        args.output = Path(f'twitter_journal_{date_str}.zip')

    try:
        # Validate input directory
        if not validate_archive(args.input):
            sys.exit(1)
        
        # Show start message
        console.print("\n[bold blue]Twitter to DayOne Converter[/bold blue]")
        console.print(f"Input directory: {args.input}")
        console.print(f"Output file: {args.output}\n")
        
        # Initialize converter
        converter = TwitterToDayOne(args.input)
        
        with Progress() as progress:
            # Load tweets
            task1 = progress.add_task("[cyan]Loading tweets...", total=None)
            converter.load_twitter_data()
            progress.update(task1, completed=True)
            
            # Convert and create zip
            console.print("\n[green]Converting tweets and processing media...[/green]")
            converter.create_export_zip(args.output)
        
        # Show completion message
        console.print("\n[bold green]✨ Conversion completed successfully![/bold green]")
        console.print("\nTo import into DayOne:")
        console.print("1. Open DayOne")
        console.print("2. Go to File -> Import -> DayOne Archive")
        console.print(f"3. Select the created file: [cyan]{args.output}[/cyan]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Conversion cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {str(e)}")
        if args.debug:
            console.print_exception()
        sys.exit(1)

if __name__ == "__main__":
    main()