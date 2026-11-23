"""Install formal catalog entries or refresh their previews.

Preview changes: python -m api.install_formal_templates
Apply: python -m api.install_formal_templates --apply
Optional preview upload: add --previews web/public/template-previews
Refresh the existing entries' previews: add --refresh-previews
"""

import argparse
import hashlib
from pathlib import Path

from sqlmodel import Session, select

from api.models import VideoTemplate
from aishorts.modules.video_edit.video_edit import VideoTemplate as TemplateSpec


FORMAL_TEMPLATES = ("lecture", "documentary", "briefing", "math", "stock_story")


def install_templates(session: Session, *, apply=False, previews: Path | None = None, refresh_previews=False):
    if refresh_previews and previews is None:
        raise ValueError("Refreshing previews requires a preview directory")
    changes = []
    for name in FORMAL_TEMPLATES:
        existing = session.exec(select(VideoTemplate).where(VideoTemplate.name == name)).first()
        legacy = (session.exec(select(VideoTemplate).where(VideoTemplate.name == "field_guide")).first()
                  if name == "stock_story" and existing is None else None)
        if existing and not refresh_previews:
            changes.append(f"Keep existing {name} (configuration and price preserved)")
            continue
        if existing:
            changes.append(f"Refresh {name} previews (configuration and price preserved)")
            template = existing
        elif legacy:
            changes.append("Replace field_guide with stock_story (price preserved)")
            template = legacy
            if apply:
                template.name = name
                template.data = {**(template.data or {}), "edit_template": name}
                template.preview_url = None
                template.thumbnail_url = None
        else:
            data = TemplateSpec(edit_template=name, template_config={}).model_dump(mode="json", exclude_unset=True)
            changes.append(f"Create {name} (1 credit per video)")
            template = VideoTemplate(name=name, data=data, credits=1)
        if apply:
            if previews:
                from aishorts.utils.r2_handler import CloudflareR2
                r2 = CloudflareR2()
                for suffix, field in ((".mp4", "preview_url"), (".png", "thumbnail_url")):
                    path = previews / f"{name}{suffix}"
                    if not path.is_file():
                        raise FileNotFoundError(path)
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
                    filename = f"{name}-{digest}{suffix}"
                    if not (getattr(template, field) or "").split("?")[0].endswith(f"/{filename}"):
                        setattr(template, field, r2.upload_file(str(path), f"assets/template-previews/{filename}"))
            session.add(template)
    if apply:
        session.commit()
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--previews", type=Path)
    parser.add_argument("--refresh-previews", action="store_true")
    args = parser.parse_args()
    if args.refresh_previews and args.previews is None:
        parser.error("--refresh-previews requires --previews")
    from api.database import engine
    with Session(engine) as session:
        for change in install_templates(session, apply=args.apply, previews=args.previews, refresh_previews=args.refresh_previews):
            print(change)
    if not args.apply:
        print("Preview only. Pass --apply to save these additions.")


if __name__ == "__main__":
    main()
