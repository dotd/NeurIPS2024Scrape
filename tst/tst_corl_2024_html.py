import pandas as pd
import os
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR
import pickle

keys = [
    "title",
    "authors",
    # "authorids",
    "keywords",
    "TLDR",
    "abstract",
    "pdf",
    "supplementary_material",
    # "venue",
    # "venueid",
    # "_bibtex",
    "website",
    # "publication_agreement",
    # "student_paper",
    "spotlight_video",
    # "paperhash",
]


def load_conference_notes_data(
    str_to_search="robot-learning_org_CoRL_2024_Conference.pkl",
):
    conferences_folder = f"{PROJECT_ROOT_DIR}/ConferencesData"
    notes_files = [f for f in os.listdir(conferences_folder) if str_to_search in f]

    notes = []
    for notes_file in notes_files:
        file_path = os.path.join(conferences_folder, notes_file)
        with open(file_path, "rb") as f:
            notes.extend(pickle.load(f))

    return notes


def notes_to_table(notes):
    reverse_keys = {v: k for k, v in enumerate(keys)}
    table = list()
    for note in notes:
        # inititate list with default value None
        row = [None] * (len(keys) + 1)
        row[0] = note.id
        for key in keys:
            if key in note.content:
                row[reverse_keys[key] + 1] = str(note.content[key]["value"])
        table.append(row)
    return table


def table_to_df(table):
    df = pd.DataFrame(table, columns=["id"] + keys)
    return df


def load_conference_data():
    # Load notes
    reverse_keys = {v: k for k, v in enumerate(keys)}
    notes = load_conference_notes_data()
    table = notes_to_table(notes)
    for i in range(len(table)):
        table[i][
            reverse_keys["spotlight_video"] + 1
        ] = f"https://openreview.net/attachment?id={table[i][0]}&name=spotlight_video"
    # https://openreview.net/attachment?id=zr2GPi3DSb&name=spotlight_video
    df = table_to_df(table)
    return df


def filter_papers_by_keywords(conferences_data, keywords, text_columns=None):
    """
    Filter papers that contain any of the given keywords in any text column.

    Args:
        conferences_data (dict): Dictionary of conference DataFrames
        keywords (list): List of keywords to search for
        text_columns (list, optional): List of column names to search in.
                                     If None, searches all object/string columns.

    Returns:
        dict: Filtered conference DataFrames containing only papers matching keywords
    """
    filtered_data = {}

    # Convert keywords to lowercase for case-insensitive matching
    keywords = [k.lower() for k in keywords]

    for conf_name, df in conferences_data.items():
        # If no columns specified, use all object/string columns
        if text_columns is None:
            text_columns = df.select_dtypes(include=["object"]).columns

        # Initialize mask as all False
        combined_mask = pd.Series(False, index=df.index)

        # Check each text column for keywords
        for column in text_columns:
            if column in df.columns:
                column_mask = (
                    df[column].str.lower().str.contains("|".join(keywords), na=False)
                )
                combined_mask = combined_mask | column_mask

        # Filter DataFrame and store if any matches found
        filtered_df = df[combined_mask]
        if len(filtered_df) > 0:
            filtered_data[conf_name] = filtered_df

    return filtered_data


def create_html_report(filtered_data):
    """
    Create an HTML report from the filtered conference data.

    Args:
        filtered_data (dict): Dictionary of filtered conference DataFrames

    Returns:
        str: HTML string containing the formatted report
    """
    html = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .paper { 
                margin-bottom: 30px;
                padding: 20px;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
            .conference { 
                font-size: 24px;
                color: #2c3e50;
                margin: 20px 0;
                padding-bottom: 10px;
                border-bottom: 2px solid #3498db;
            }
            .field-name {
                font-weight: bold;
                color: #2980b9;
            }
            .field-value {
                margin-bottom: 10px;
                line-break: anywhere;
            }
            a { color: #3498db; }
            a:hover { color: #2980b9; }
            .paper-counter {
                font-size: 18px;
                color: #2c3e50;
                margin: 20px 0;
                padding-bottom: 10px;
                border-bottom: 2px solid #3498db;
            }
        </style>
    </head>
    <body>
    """
    # Add total paper count across all conferences
    total_papers = len(filtered_data)
    paper_counter = 0

    for _, paper in filtered_data.iterrows():
        paper_counter += 1
        html += '<div class="paper">\n'

        # Add each field from the paper
        for field in paper.index:
            value = paper[field]
            if pd.notna(value):  # Only show non-null values
                html += f'<div class="field-name">{field}:</div>\n'

                # Special handling for URLs (pdf and supplementary_material)
                if field in [
                    "pdf",
                    "supplementary_material",
                    "spotlight_video",
                    "website",
                ] and isinstance(value, str):
                    html += f'<div class="field-value"><a href="{value}" target="_blank">{value}</a></div>\n'
                else:
                    html += f'<div class="field-value">{value}</div>\n'

        html += "</div>\n"

        html += f"<div class='paper-counter'>{paper_counter}/{total_papers}</div>\n"

    html += """
    </body>
    </html>
    """

    return html


if __name__ == "__main__":
    conferences_data = load_conference_data()
    htmls_folder = "htmls"
    html_report = create_html_report(conferences_data)
    # Save the HTML file
    if not os.path.exists(f"{PROJECT_ROOT_DIR}/{htmls_folder}"):
        os.makedirs(f"{PROJECT_ROOT_DIR}/{htmls_folder}")
    with open(
        f"{PROJECT_ROOT_DIR}/{htmls_folder}/corl_2024_papers_report2.html",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(html_report)
