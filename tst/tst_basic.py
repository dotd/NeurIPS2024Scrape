import os
from OpenreviewScrape import openreview_utils, drive_utils
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR


def scrape_neurips_2024():
    args = openreview_utils.prepare_parameters_and_logging(
        arguments=[
            ["--credentials_file", str, f"{PROJECT_ROOT_DIR}/credentials/openreview_api.txt"],
            ["--cache_folder", str, f"{PROJECT_ROOT_DIR}/cache/"],
            ["--venue_id", str, "NeurIPS.cc/2024/Conference"],
        ],
    )

    notes = openreview_utils.get_conference(
        credentials_file=args.credentials_file,
        venue_id=args.venue_id,
        cache_folder=args.cache_folder
    )
    # Open link to google drive and make a new sheet

    table = list()
    fields = ['title',
              'authors',
              'keywords',
              'TLDR',
              'abstract',
              'primary_area',
              'venue',
              'pdf',
              'supplementary_material']
    for note in notes:
        # print(note.content['title'])
        line = list()
        if ("poster" not in note.content["venue"]["value"] and
                "spotlight" not in note.content["venue"]["value"] and
                "talk" not in note.content["venue"]["value"]):
            continue
        for field in fields:
            if field in note.content:
                value = note.content[field]["value"] if type(note.content[field]["value"]) == str \
                    else ";".join(note.content[field]["value"])
                if field == "pdf" or field == "supplementary_material":
                    value = f'https://openreview.net{value}'
                value = value.replace("\t", "").replace("\n", "")
                line.append(value)
            else:
                line.append("")
        table.append("\t".join(line))
    table = "\n".join(table)
    # if data folder does not exist, create it
    if not os.path.exists(f"{PROJECT_ROOT_DIR}/data"):
        os.makedirs(f"{PROJECT_ROOT_DIR}/data")

    # save table to file
    with open(f"{PROJECT_ROOT_DIR}/data/neurips_2024.csv", "w") as f:
        f.write(table)
    """
    # create new sheet in google drive
    drive, guath = drive_utils.get_gdrive_login_credentials()
    service = drive_utils.get_sheets_service(guath)
    file_id = drive_utils.create_new_sheet(drive, "NeurIPS 2024")
    drive_utils.insert_values_into_sheet(service, file_id)
    """
    # save notes to sheet


if __name__ == "__main__":
    scrape_neurips_2024()
