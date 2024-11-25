# X/Twitter to Day One Converter
Add your Tweets to [Day One](https://dayoneapp.com)! The converter will create a Day One-compatible ZIP file that you can import into your Day One journal. Each tweet will become a journal entry with the original timestamp, text, tags, and any attached media.

Requires python 3.

*Usage:*
* Get an export of your X/Twitter data from [X/Twitter](https://x.com/settings/download_your_data)
* `pip install rich rqdm`
* `python x-to-dayone.py -i /path/to/x-export-folder -o x-journal.zip`
