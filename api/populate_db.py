import os
import sys

# Add project root to sys.path to allow imports from api and src
sys.path.append(os.getcwd())

from sqlmodel import Session, select
from api.database import engine, create_db_and_tables
from api.models import Avatar, VideoTemplate
from aishorts.utils.pydantic_helper import load_pydantic_dict
from aishorts.modules.avatar import Avatar as PydanticAvatar
from aishorts.modules.video_edit.video_edit import (
    VideoTemplate as PydanticVideoTemplate,
)


def populate_db():
    print("Initializing Database...")
    create_db_and_tables()

    with Session(engine) as session:
        # --- 1. Populate Avatars ---
        print("\nSyncing Avatars...")
        avatars_path = "cli/configs/avatars.json"
        if os.path.exists(avatars_path):
            # Returns dict[str, PydanticAvatar]
            avatars_map = load_pydantic_dict(avatars_path, PydanticAvatar)

            for key, pydantic_obj in avatars_map.items():
                # Check if exists by name (key)
                statement = select(Avatar).where(Avatar.name == key)
                existing = session.exec(statement).first()

                # Serialize Pydantic model to dict (handles v1/v2 compatibility)
                data_dict = getattr(pydantic_obj, "model_dump", pydantic_obj.dict)()

                if existing:
                    existing.data = data_dict
                    session.add(existing)
                    print(f"  [UPDATED] {key}")
                else:
                    new_avatar = Avatar(name=key, data=data_dict)
                    session.add(new_avatar)
                    print(f"  [CREATED] {key}")
        else:
            print(f"  [ERROR] File not found: {avatars_path}")

        # --- 2. Populate Video Templates ---
        print("\nSyncing Video Templates...")
        templates_path = "cli/configs/video_templates.json"
        if os.path.exists(templates_path):
            templates_map = load_pydantic_dict(templates_path, PydanticVideoTemplate)

            for key, pydantic_obj in templates_map.items():
                statement = select(VideoTemplate).where(VideoTemplate.name == key)
                existing = session.exec(statement).first()

                data_dict = getattr(pydantic_obj, "model_dump", pydantic_obj.dict)()

                if existing:
                    existing.data = data_dict
                    session.add(existing)
                    print(f"  [UPDATED] {key}")
                else:
                    new_template = VideoTemplate(name=key, data=data_dict)
                    session.add(new_template)
                    print(f"  [CREATED] {key}")
        else:
            print(f"  [ERROR] File not found: {templates_path}")

        session.commit()
        print("\nDatabase sync complete!")


if __name__ == "__main__":
    populate_db()
