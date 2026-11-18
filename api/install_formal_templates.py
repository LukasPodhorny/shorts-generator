"""Install only the new catalog entries, preserving existing rows and prices.

Preview changes: python -m api.install_formal_templates
Apply: python -m api.install_formal_templates --apply
Optional preview upload: add --previews web/public/template-previews
"""

import argparse
from pathlib import Path

from sqlmodel import Session, select

from api.models import VideoTemplate
from aishorts.modules.video_edit.video_edit import VideoTemplate as TemplateSpec


FORMAL_TEMPLATES = ("lecture", "documentary", "briefing")


def install_templates(session: Session, *, apply=False, previews: Path | None = None):
    changes = []
    for name in FORMAL_TEMPLATES:
        existing = session.exec(select(VideoTemplate).where(VideoTemplate.name == name)).first()
        if existing:
            changes.append(f"Keep existing {name} (configuration and price preserved)")
            continue
        data = TemplateSpec(edit_template=name, template_config={}).model_dump(mode="json", exclude_unset=True)
        changes.append(f"Create {name} (1 credit per video)")
        if apply:
            template = VideoTemplate(name=name, data=data, credits=1)
            if previews:
                from aishorts.utils.r2_handler import CloudflareR2
                r2 = CloudflareR2()
                for suffix, field in ((".mp4", "preview_url"), (".png", "thumbnail_url")):
                    path = previews / f"{name}{suffix}"
                    if not path.is_file():
                        raise FileNotFoundError(path)
                    setattr(template, field, r2.upload_file(str(path), f"assets/template-previews/{path.name}"))
            session.add(template)
    if apply:
        session.commit()
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--previews", type=Path)
    args = parser.parse_args()
    from api.database import engine
    with Session(engine) as session:
        for change in install_templates(session, apply=args.apply, previews=args.previews):
            print(change)
    if not args.apply:
        print("Preview only. Pass --apply to save these additions.")


if __name__ == "__main__":
    main()
