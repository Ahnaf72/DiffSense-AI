import re

def remove_references(text):
    # remove "References", "Bibliography" section
    text = re.split(r'References|Bibliography', text, flags=re.IGNORECASE)[0]

    # remove citations like (Smith, 2020)
    text = re.sub(r"\(.*?\d{4}.*?\)", "", text)

    # remove [1], [2]
    text = re.sub(r"\[\d+\]", "", text)

    return text