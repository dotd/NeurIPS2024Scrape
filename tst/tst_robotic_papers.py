import pandas as pd
import os
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR


def load_conference_data():
    conferences_data = {}
    conferences_folder = f"{PROJECT_ROOT_DIR}/ConferencesData"

    # Get all CSV files in the folder
    csv_files = [f for f in os.listdir(conferences_folder) if f.endswith(".csv")]

    # Load each CSV file into a pandas DataFrame
    for csv_file in csv_files:
        file_path = os.path.join(conferences_folder, csv_file)
        # Read CSV with tab separator since the files use \t

        print(f"Loading {csv_file}")

        # Read raw lines first and split by tabs
        with open(file_path, "r") as f:
            lines = f.readlines()
            data = [line.strip().split("\t") for line in lines]
        # Check that all lines have the same number of fields
        expected_fields = 9  # Based on the columns defined below
        invalid_lines = [
            i for i, line in enumerate(data) if len(line) != expected_fields
        ]

        if invalid_lines:
            print(
                f"Warning: Found {len(invalid_lines)} lines with incorrect number of fields in {csv_file}"
            )
            print(f"Expected {expected_fields} fields, but found:")
            for i in invalid_lines:
                print(f"Line {i}: {len(data[i])} fields")
                print(f"Content: {data[i]}")
            # Filter out invalid lines
            data = [line for line in data if len(line) == expected_fields]

        # Remove lines that were identified as having incorrect number of fields
        data = [line for i, line in enumerate(data) if i not in invalid_lines]

        # Create DataFrame from the raw data
        df = pd.DataFrame(
            data,
            columns=[
                "title",
                "authors",
                "keywords",
                "primary_area",
                "venue",
                "pdf",
                "supplementary_material",
                "TLDR",
                "abstract",
            ],
        )
        conferences_data[csv_file] = df

    return conferences_data


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
    total_papers = sum(len(df) for df in filtered_data.values())
    paper_counter = 0

    for conf_name, df in filtered_data.items():
        html += f'<div class="conference">{conf_name}</div>\n'

        for _, paper in df.iterrows():
            paper_counter += 1
            html += '<div class="paper">\n'

            # Add each field from the paper
            for field in paper.index:
                value = paper[field]
                if pd.notna(value):  # Only show non-null values
                    html += f'<div class="field-name">{field}:</div>\n'

                    # Special handling for URLs (pdf and supplementary_material)
                    if field in ["pdf", "supplementary_material"] and isinstance(
                        value, str
                    ):
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
    filtered_data = filter_papers_by_keywords(
        conferences_data, ["robotic", "manipulation", "manipulator", "robot"]
    )
    html_report = create_html_report(conferences_data)
    # Save the HTML file
    if not os.path.exists(f"{PROJECT_ROOT_DIR}/{htmls_folder}"):
        os.makedirs(f"{PROJECT_ROOT_DIR}/{htmls_folder}")
    with open(
        f"{PROJECT_ROOT_DIR}/{htmls_folder}/all_papers_report.html",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(html_report)
