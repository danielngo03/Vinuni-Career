/**
 * A realistic sample CV used to render template gallery thumbnails. Because
 * thumbnails always render the SAME sample through each template's theme, the
 * cards differ only by design (colour + layout), which is exactly what we want
 * a student to compare. Bilingual-friendly (VN name, EN role content) so both
 * vi/en galleries read naturally.
 *
 * The shape mirrors {@link CvDocumentContent} (see `cv-document.tsx`) so the one
 * renderer consumes sample content and real CV detail content identically.
 */

import type { CvDocumentContent } from "./cv-document";

export const SAMPLE_CV: CvDocumentContent = {
  header: {
    name: "Nguyễn Minh Anh",
    headline: "Product-minded Software Engineer",
    email: "minhanh.nguyen@vinuni.edu.vn",
    phone: "+84 90 123 4567",
    location: "Hà Nội, Việt Nam",
    links: [
      { label: "github.com/minhanh", url: "https://github.com/minhanh" },
      { label: "linkedin.com/in/minhanh", url: "https://linkedin.com/in/minhanh" },
    ],
  },
  sections: [
    {
      id: "s-summary",
      section_type: "summary",
      title: "Summary",
      is_visible: true,
      sort_order: 10,
      kind: "text",
      text:
        "Final-year Computer Science student at VinUniversity with hands-on " +
        "experience shipping full-stack products. Comfortable across React, " +
        "Python and cloud infrastructure, and driven by clean, measurable impact.",
    },
    {
      id: "s-experience",
      section_type: "experience",
      title: "Experience",
      is_visible: true,
      sort_order: 20,
      kind: "entries",
      entries: [
        {
          heading: "Software Engineer Intern",
          subheading: "FPT Software",
          timeframe: "Jun 2025 – Sep 2025",
          location: "Hà Nội",
          highlights: [
            "Built a document-parsing pipeline that cut manual review time by 40%.",
            "Shipped a React dashboard used daily by 30+ operations staff.",
            "Wrote integration tests raising service coverage from 55% to 88%.",
          ],
        },
        {
          heading: "Research Assistant",
          subheading: "VinUni AI Lab",
          timeframe: "Jan 2025 – May 2025",
          location: "Hà Nội",
          highlights: [
            "Co-authored a paper on low-resource OCR for Vietnamese documents.",
            "Automated dataset labelling, saving the team ~10 hours per week.",
          ],
        },
      ],
    },
    {
      id: "s-education",
      section_type: "education",
      title: "Education",
      is_visible: true,
      sort_order: 30,
      kind: "entries",
      entries: [
        {
          heading: "B.Sc. Computer Science",
          subheading: "VinUniversity",
          timeframe: "2022 – 2026",
          location: "Hà Nội",
          highlights: ["GPA 3.8 / 4.0 · Dean's List (4 semesters)"],
        },
      ],
    },
    {
      id: "s-projects",
      section_type: "projects",
      title: "Projects",
      is_visible: true,
      sort_order: 40,
      kind: "entries",
      entries: [
        {
          heading: "CampusHub",
          subheading: "Next.js · FastAPI · PostgreSQL",
          timeframe: "2025",
          highlights: [
            "Event platform adopted by 5 student clubs with 1,200+ sign-ups.",
          ],
        },
      ],
    },
    {
      id: "s-skills",
      section_type: "skills",
      title: "Skills",
      is_visible: true,
      sort_order: 50,
      kind: "skills",
      skills: [
        { name: "TypeScript", level: 90 },
        { name: "React / Next.js", level: 88 },
        { name: "Python", level: 82 },
        { name: "PostgreSQL", level: 75 },
        { name: "AWS", level: 68 },
        { name: "Docker", level: 62 },
      ],
    },
    {
      id: "s-languages",
      section_type: "languages",
      title: "Languages",
      is_visible: true,
      sort_order: 60,
      kind: "languages",
      languages: [
        { name: "Vietnamese", level: 100 },
        { name: "English", level: 85 },
        { name: "Japanese", level: 40 },
      ],
    },
    {
      id: "s-certifications",
      section_type: "certifications",
      title: "Certifications",
      is_visible: true,
      sort_order: 70,
      kind: "entries",
      entries: [
        {
          heading: "AWS Certified Cloud Practitioner",
          subheading: "Amazon Web Services",
          timeframe: "2025",
          highlights: [],
        },
      ],
    },
    {
      id: "s-interests",
      section_type: "interests",
      title: "Interests",
      is_visible: true,
      sort_order: 80,
      kind: "text",
      text: "Open-source, competitive programming, and product design.",
    },
  ],
};
