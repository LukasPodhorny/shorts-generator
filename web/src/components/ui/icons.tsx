import type { ReactElement, ReactNode, SVGProps } from 'react';
import type { FileCategory } from '@/lib/sourceFiles';

// Minimal inline SVG icon set (Material Symbols-style paths) so we don't pull
// in an icon dependency. `size` controls width/height; color is currentColor.
type IconProps = { size?: number } & SVGProps<SVGSVGElement>;

function Svg({ size = 24, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M11 13H5v-2h6V5h2v6h6v2h-6v6h-2z" />
  </Svg>
);

export const CloseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M18.3 5.71 12 12l6.3 6.29-1.42 1.42L10.59 13.4 4.3 19.7 2.88 18.3 9.17 12 2.88 5.71 4.3 4.29l6.29 6.3 6.29-6.3z" />
  </Svg>
);

export const LinkIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3.9 12a3.1 3.1 0 0 1 3.1-3.1h4V7H7a5 5 0 0 0 0 10h4v-1.9H7A3.1 3.1 0 0 1 3.9 12M8 13h8v-2H8zm9-6h-4v1.9h4a3.1 3.1 0 0 1 0 6.2h-4V17h4a5 5 0 0 0 0-10" />
  </Svg>
);

export const SearchIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 5L20.49 19zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14" />
  </Svg>
);

export const AttachFileIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M16.5 6v11.5a4 4 0 0 1-8 0V5a2.5 2.5 0 0 1 5 0v10.5a1 1 0 0 1-2 0V6H10v9.5a2.5 2.5 0 0 0 5 0V5a4 4 0 0 0-8 0v12.5a5.5 5.5 0 0 0 11 0V6z" />
  </Svg>
);

export const GlobeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m6.9 6h-2.95a15.7 15.7 0 0 0-1.38-3.56A8 8 0 0 1 18.92 8M12 4c.83 1.2 1.48 2.53 1.91 3.96h-3.82A13 13 0 0 1 12 4M4.26 14a7.8 7.8 0 0 1 0-4h3.38a16.5 16.5 0 0 0 0 4zm.82 2h2.95a15.7 15.7 0 0 0 1.38 3.56A8 8 0 0 1 5.08 16m2.95-8H5.08a8 8 0 0 1 4.33-3.56A15.7 15.7 0 0 0 8.03 8M12 20a13 13 0 0 1-1.91-4h3.82A13 13 0 0 1 12 20m2.34-6H9.66a14.7 14.7 0 0 1 0-4h4.68a14.7 14.7 0 0 1 0 4m.25 5.56A15.7 15.7 0 0 0 15.97 16h2.95a8 8 0 0 1-4.33 3.56M16.36 14a16.5 16.5 0 0 0 0-4h3.38a7.8 7.8 0 0 1 0 4z" />
  </Svg>
);

export const ErrorIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m1 15h-2v-2h2zm0-4h-2V7h2z" />
  </Svg>
);

export const PersonIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10m0 2c-3.34 0-10 1.67-10 5v3h20v-3c0-3.33-6.66-5-10-5" />
  </Svg>
);

// --- File-category glyphs (used by source chips) ---
const PdfIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm7 1.5L18.5 9H13zM8 13h1.5a1.5 1.5 0 0 1 0 3H9v2H8zm1 2h.5a.5.5 0 0 0 0-1H9zm3-2h1.5a1.5 1.5 0 0 1 1.5 1.5v0A1.5 1.5 0 0 1 13.5 16H13v2h-1zm1 2h.5a.5.5 0 0 0 .5-.5.5.5 0 0 0-.5-.5H13zm3-2h2v1h-1v.75h1v1h-1V18h-1z" />
  </Svg>
);
const SlidesIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 4h18v2H3zm1 3h16v10a1 1 0 0 1-1 1h-5v2h-2v-2H5a1 1 0 0 1-1-1zm4 3v6l5-3z" />
  </Svg>
);
const DocIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm7 1.5L18.5 9H13zM8 12h8v1.5H8zm0 3h8v1.5H8zm0 3h5v1.5H8z" />
  </Svg>
);
const SheetIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4h16v16H4zm2 2v3h5V6zm7 0v3h5V6zm5 5h-5v3h5zm0 5h-5v3h5zm-7 3v-3H6v3zm-5-5h5v-3H6z" />
  </Svg>
);
const TextIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 4h14v2H5zm0 5h14v2H5zm0 5h10v2H5z" />
  </Svg>
);
const ImageIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1m1 13h14l-4.5-6-3.5 4.5L9 13zM8.5 9.5A1.5 1.5 0 1 0 7 8a1.5 1.5 0 0 0 1.5 1.5" />
  </Svg>
);
const AudioIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3z" />
  </Svg>
);
const GenericFileIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm7 1.5L18.5 9H13z" />
  </Svg>
);

const FILE_ICONS: Record<FileCategory, (p: IconProps) => ReactElement> = {
  pdf: PdfIcon,
  slides: SlidesIcon,
  doc: DocIcon,
  sheet: SheetIcon,
  text: TextIcon,
  image: ImageIcon,
  audio: AudioIcon,
  file: GenericFileIcon,
};

export function FileCategoryIcon({ category, ...rest }: { category: FileCategory } & IconProps) {
  const Icon = FILE_ICONS[category];
  return <Icon {...rest} />;
}
