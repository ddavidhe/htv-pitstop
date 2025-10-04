from datetime import datetime

def convert_date_to_iso(date_str):
    """Convert 'Sept 22' format to a datetime object"""
    current_year = datetime.now().year
    
    # Dictionary to map month abbreviations to numbers
    month_map = {
        'Jan': '01', 'January': '01',
        'Feb': '02', 'February': '02',
        'Mar': '03', 'March': '03',
        'Apr': '04', 'April': '04',
        'May': '05',
        'Jun': '06', 'June': '06',
        'Jul': '07', 'July': '07',
        'Aug': '08', 'August': '08',
        'Sep': '09', 'Sept': '09', 'September': '09',
        'Oct': '10', 'October': '10',
        'Nov': '11', 'November': '11',
        'Dec': '12', 'December': '12'
    }
    
    # Extract month and day
    parts = date_str.split()
    if len(parts) == 2:
        month_abbr = parts[0]
        day = parts[1].zfill(2)  # Add leading zero if needed
        
        if month_abbr in month_map:
            month = int(month_map[month_abbr])
            day = int(day)
            return datetime(current_year, month, day)
    
    return None  # Return None if can't parse


if __name__ == "__main__":
    # Example usage of the functions
    test_date = "Sept 22"
    
    iso_date = convert_date_to_iso(test_date)
    if iso_date:
        print(f"Converted date: {iso_date}")
    else:
        print("Failed to convert date.")
