"""Industry taxonomy seed data — 3-level hierarchy, bilingual (vi + en).

Sources: TopCV 2025-2026 Recruitment Report, VietnamWorks category list,
         Vietnam Standard Industrial Classification (VSIC 2025), ISCO-08.

Structure:
  root (level 0) → branch (level 1) → leaf (level 2)
  e.g. "Công nghệ thông tin" → "Khoa học dữ liệu" → "Phân tích dữ liệu"
"""

from __future__ import annotations

INDUSTRY_TREE: list[dict] = [
    # ════════════════════════════════════════════════════════════════════════
    # 1. Công nghệ thông tin / Information Technology
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "information-technology",
        "name_vi": "Công nghệ thông tin",
        "name_en": "Information Technology",
        "sort_order": 1,
        "children": [
            {
                "slug": "software-development",
                "name_vi": "Phát triển phần mềm",
                "name_en": "Software Development",
                "sort_order": 1,
                "children": [
                    {"slug": "frontend-development", "name_vi": "Lập trình Frontend", "name_en": "Frontend Development", "sort_order": 1},
                    {"slug": "backend-development", "name_vi": "Lập trình Backend", "name_en": "Backend Development", "sort_order": 2},
                    {"slug": "fullstack-development", "name_vi": "Lập trình Full-stack", "name_en": "Full-stack Development", "sort_order": 3},
                    {"slug": "mobile-development", "name_vi": "Lập trình ứng dụng di động", "name_en": "Mobile App Development", "sort_order": 4},
                    {"slug": "embedded-systems", "name_vi": "Lập trình nhúng", "name_en": "Embedded Systems", "sort_order": 5},
                    {"slug": "game-development", "name_vi": "Lập trình game", "name_en": "Game Development", "sort_order": 6},
                ],
            },
            {
                "slug": "data-science",
                "name_vi": "Khoa học dữ liệu",
                "name_en": "Data Science",
                "sort_order": 2,
                "children": [
                    {"slug": "data-analyst", "name_vi": "Phân tích dữ liệu", "name_en": "Data Analysis", "sort_order": 1},
                    {"slug": "data-engineering", "name_vi": "Kỹ thuật dữ liệu", "name_en": "Data Engineering", "sort_order": 2},
                    {"slug": "machine-learning", "name_vi": "Học máy", "name_en": "Machine Learning", "sort_order": 3},
                    {"slug": "ai-engineering", "name_vi": "Kỹ thuật AI", "name_en": "AI Engineering", "sort_order": 4},
                    {"slug": "business-intelligence", "name_vi": "Phân tích thông minh doanh nghiệp", "name_en": "Business Intelligence", "sort_order": 5},
                    {"slug": "data-science-research", "name_vi": "Nghiên cứu khoa học dữ liệu", "name_en": "Data Science Research", "sort_order": 6},
                ],
            },
            {
                "slug": "cybersecurity",
                "name_vi": "An ninh mạng",
                "name_en": "Cybersecurity",
                "sort_order": 3,
                "children": [
                    {"slug": "penetration-testing", "name_vi": "Kiểm thử xâm nhập", "name_en": "Penetration Testing", "sort_order": 1},
                    {"slug": "security-operations", "name_vi": "Vận hành bảo mật (SOC)", "name_en": "Security Operations (SOC)", "sort_order": 2},
                    {"slug": "cloud-security", "name_vi": "Bảo mật đám mây", "name_en": "Cloud Security", "sort_order": 3},
                    {"slug": "network-security", "name_vi": "Bảo mật mạng", "name_en": "Network Security", "sort_order": 4},
                ],
            },
            {
                "slug": "it-infrastructure",
                "name_vi": "Hạ tầng & Mạng máy tính",
                "name_en": "IT Infrastructure & Networks",
                "sort_order": 4,
                "children": [
                    {"slug": "network-administration", "name_vi": "Quản trị mạng", "name_en": "Network Administration", "sort_order": 1},
                    {"slug": "system-administration", "name_vi": "Quản trị hệ thống", "name_en": "System Administration", "sort_order": 2},
                    {"slug": "cloud-computing", "name_vi": "Điện toán đám mây", "name_en": "Cloud Computing", "sort_order": 3},
                    {"slug": "devops", "name_vi": "DevOps / SRE", "name_en": "DevOps / SRE", "sort_order": 4},
                    {"slug": "database-administration", "name_vi": "Quản trị cơ sở dữ liệu", "name_en": "Database Administration", "sort_order": 5},
                ],
            },
            {
                "slug": "qa-testing",
                "name_vi": "Kiểm thử phần mềm (QA/QC)",
                "name_en": "Software QA / Testing",
                "sort_order": 5,
                "children": [
                    {"slug": "manual-testing", "name_vi": "Kiểm thử thủ công", "name_en": "Manual Testing", "sort_order": 1},
                    {"slug": "test-automation", "name_vi": "Kiểm thử tự động", "name_en": "Test Automation", "sort_order": 2},
                    {"slug": "performance-testing", "name_vi": "Kiểm thử hiệu năng", "name_en": "Performance Testing", "sort_order": 3},
                ],
            },
            {
                "slug": "it-project-management",
                "name_vi": "Quản lý dự án CNTT",
                "name_en": "IT Project Management",
                "sort_order": 6,
                "children": [
                    {"slug": "product-management", "name_vi": "Quản lý sản phẩm", "name_en": "Product Management", "sort_order": 1},
                    {"slug": "scrum-agile", "name_vi": "Scrum Master / Agile Coach", "name_en": "Scrum Master / Agile Coach", "sort_order": 2},
                    {"slug": "business-analyst-it", "name_vi": "Phân tích nghiệp vụ (BA)", "name_en": "Business Analyst (IT)", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 2. Kinh doanh / Bán hàng
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "business-sales",
        "name_vi": "Kinh doanh / Bán hàng",
        "name_en": "Business / Sales",
        "sort_order": 2,
        "children": [
            {
                "slug": "b2b-sales",
                "name_vi": "Bán hàng doanh nghiệp (B2B)",
                "name_en": "B2B Sales",
                "sort_order": 1,
                "children": [
                    {"slug": "key-account-management", "name_vi": "Quản lý khách hàng trọng yếu (KAM)", "name_en": "Key Account Management", "sort_order": 1},
                    {"slug": "enterprise-sales", "name_vi": "Bán hàng doanh nghiệp lớn", "name_en": "Enterprise Sales", "sort_order": 2},
                    {"slug": "solution-sales", "name_vi": "Bán giải pháp / tư vấn", "name_en": "Solution / Consultative Sales", "sort_order": 3},
                ],
            },
            {
                "slug": "b2c-sales",
                "name_vi": "Bán hàng người tiêu dùng (B2C)",
                "name_en": "B2C / Retail Sales",
                "sort_order": 2,
                "children": [
                    {"slug": "retail-sales", "name_vi": "Bán lẻ trực tiếp", "name_en": "Retail Sales", "sort_order": 1},
                    {"slug": "telesales", "name_vi": "Bán hàng qua điện thoại", "name_en": "Telesales", "sort_order": 2},
                    {"slug": "online-sales", "name_vi": "Bán hàng trực tuyến / e-commerce", "name_en": "Online / E-commerce Sales", "sort_order": 3},
                ],
            },
            {
                "slug": "business-development",
                "name_vi": "Phát triển kinh doanh",
                "name_en": "Business Development",
                "sort_order": 3,
                "children": [
                    {"slug": "partnership-development", "name_vi": "Phát triển đối tác", "name_en": "Partnership Development", "sort_order": 1},
                    {"slug": "market-expansion", "name_vi": "Mở rộng thị trường", "name_en": "Market Expansion", "sort_order": 2},
                    {"slug": "franchise-distribution", "name_vi": "Nhượng quyền / Phân phối", "name_en": "Franchise & Distribution", "sort_order": 3},
                ],
            },
            {
                "slug": "sales-management",
                "name_vi": "Quản lý kinh doanh",
                "name_en": "Sales Management",
                "sort_order": 4,
                "children": [
                    {"slug": "regional-sales-manager", "name_vi": "Quản lý kinh doanh vùng", "name_en": "Regional Sales Manager", "sort_order": 1},
                    {"slug": "sales-director", "name_vi": "Giám đốc kinh doanh", "name_en": "Sales Director", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 3. Marketing / PR / Quảng cáo
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "marketing-pr",
        "name_vi": "Marketing / PR / Quảng cáo",
        "name_en": "Marketing / PR / Advertising",
        "sort_order": 3,
        "children": [
            {
                "slug": "digital-marketing",
                "name_vi": "Marketing kỹ thuật số",
                "name_en": "Digital Marketing",
                "sort_order": 1,
                "children": [
                    {"slug": "seo-sem", "name_vi": "SEO / SEM", "name_en": "SEO / SEM", "sort_order": 1},
                    {"slug": "social-media-marketing", "name_vi": "Marketing mạng xã hội", "name_en": "Social Media Marketing", "sort_order": 2},
                    {"slug": "email-marketing", "name_vi": "Email Marketing", "name_en": "Email Marketing", "sort_order": 3},
                    {"slug": "performance-marketing", "name_vi": "Performance Marketing", "name_en": "Performance Marketing", "sort_order": 4},
                    {"slug": "content-marketing", "name_vi": "Content Marketing", "name_en": "Content Marketing", "sort_order": 5},
                    {"slug": "growth-hacking", "name_vi": "Growth Hacking", "name_en": "Growth Hacking", "sort_order": 6},
                ],
            },
            {
                "slug": "brand-management",
                "name_vi": "Quản lý thương hiệu",
                "name_en": "Brand Management",
                "sort_order": 2,
                "children": [
                    {"slug": "brand-strategy", "name_vi": "Chiến lược thương hiệu", "name_en": "Brand Strategy", "sort_order": 1},
                    {"slug": "brand-identity", "name_vi": "Nhận diện thương hiệu", "name_en": "Brand Identity", "sort_order": 2},
                ],
            },
            {
                "slug": "public-relations",
                "name_vi": "Quan hệ công chúng (PR)",
                "name_en": "Public Relations",
                "sort_order": 3,
                "children": [
                    {"slug": "media-relations", "name_vi": "Quan hệ báo chí / truyền thông", "name_en": "Media Relations", "sort_order": 1},
                    {"slug": "corporate-communications", "name_vi": "Truyền thông doanh nghiệp", "name_en": "Corporate Communications", "sort_order": 2},
                    {"slug": "crisis-management", "name_vi": "Quản lý khủng hoảng truyền thông", "name_en": "Crisis Communications", "sort_order": 3},
                ],
            },
            {
                "slug": "event-marketing",
                "name_vi": "Tổ chức sự kiện / Activation",
                "name_en": "Event Marketing / Activation",
                "sort_order": 4,
                "children": [
                    {"slug": "event-planning", "name_vi": "Lên kế hoạch sự kiện", "name_en": "Event Planning", "sort_order": 1},
                    {"slug": "sponsorship-activation", "name_vi": "Sponsorship & Activation", "name_en": "Sponsorship & Activation", "sort_order": 2},
                ],
            },
            {
                "slug": "market-research",
                "name_vi": "Nghiên cứu thị trường",
                "name_en": "Market Research",
                "sort_order": 5,
                "children": [
                    {"slug": "consumer-insights", "name_vi": "Nghiên cứu người tiêu dùng", "name_en": "Consumer Insights", "sort_order": 1},
                    {"slug": "competitive-intelligence", "name_vi": "Phân tích cạnh tranh", "name_en": "Competitive Intelligence", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 4. Tài chính / Ngân hàng / Bảo hiểm
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "finance-banking-insurance",
        "name_vi": "Tài chính / Ngân hàng / Bảo hiểm",
        "name_en": "Finance / Banking / Insurance",
        "sort_order": 4,
        "children": [
            {
                "slug": "banking",
                "name_vi": "Ngân hàng",
                "name_en": "Banking",
                "sort_order": 1,
                "children": [
                    {"slug": "retail-banking", "name_vi": "Ngân hàng bán lẻ", "name_en": "Retail Banking", "sort_order": 1},
                    {"slug": "corporate-banking", "name_vi": "Ngân hàng doanh nghiệp", "name_en": "Corporate Banking", "sort_order": 2},
                    {"slug": "investment-banking", "name_vi": "Ngân hàng đầu tư", "name_en": "Investment Banking", "sort_order": 3},
                    {"slug": "credit-risk", "name_vi": "Quản trị rủi ro tín dụng", "name_en": "Credit Risk", "sort_order": 4},
                    {"slug": "trade-finance", "name_vi": "Tài trợ thương mại", "name_en": "Trade Finance", "sort_order": 5},
                ],
            },
            {
                "slug": "investment-securities",
                "name_vi": "Đầu tư / Chứng khoán",
                "name_en": "Investment / Securities",
                "sort_order": 2,
                "children": [
                    {"slug": "fund-management", "name_vi": "Quản lý quỹ", "name_en": "Fund Management", "sort_order": 1},
                    {"slug": "equity-research", "name_vi": "Phân tích cổ phiếu", "name_en": "Equity Research", "sort_order": 2},
                    {"slug": "brokerage", "name_vi": "Môi giới chứng khoán", "name_en": "Brokerage", "sort_order": 3},
                    {"slug": "private-equity-vc", "name_vi": "Cổ phần tư nhân / VC", "name_en": "Private Equity / VC", "sort_order": 4},
                ],
            },
            {
                "slug": "insurance",
                "name_vi": "Bảo hiểm",
                "name_en": "Insurance",
                "sort_order": 3,
                "children": [
                    {"slug": "life-insurance", "name_vi": "Bảo hiểm nhân thọ", "name_en": "Life Insurance", "sort_order": 1},
                    {"slug": "general-insurance", "name_vi": "Bảo hiểm phi nhân thọ", "name_en": "General Insurance", "sort_order": 2},
                    {"slug": "actuarial", "name_vi": "Định phí bảo hiểm (Actuarial)", "name_en": "Actuarial", "sort_order": 3},
                ],
            },
            {
                "slug": "corporate-finance",
                "name_vi": "Tài chính doanh nghiệp",
                "name_en": "Corporate Finance",
                "sort_order": 4,
                "children": [
                    {"slug": "financial-planning-analysis", "name_vi": "Lập kế hoạch & phân tích tài chính (FP&A)", "name_en": "Financial Planning & Analysis (FP&A)", "sort_order": 1},
                    {"slug": "treasury", "name_vi": "Quản lý ngân quỹ", "name_en": "Treasury", "sort_order": 2},
                    {"slug": "mergers-acquisitions", "name_vi": "Mua bán & sáp nhập (M&A)", "name_en": "Mergers & Acquisitions (M&A)", "sort_order": 3},
                ],
            },
            {
                "slug": "fintech",
                "name_vi": "Công nghệ tài chính (Fintech)",
                "name_en": "Fintech",
                "sort_order": 5,
                "children": [
                    {"slug": "digital-payments", "name_vi": "Thanh toán số", "name_en": "Digital Payments", "sort_order": 1},
                    {"slug": "blockchain-crypto", "name_vi": "Blockchain / Crypto", "name_en": "Blockchain / Crypto", "sort_order": 2},
                    {"slug": "lending-tech", "name_vi": "Công nghệ cho vay", "name_en": "Lending Tech", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 5. Kế toán / Kiểm toán
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "accounting-auditing",
        "name_vi": "Kế toán / Kiểm toán",
        "name_en": "Accounting / Auditing",
        "sort_order": 5,
        "children": [
            {
                "slug": "general-accounting",
                "name_vi": "Kế toán tổng hợp",
                "name_en": "General Accounting",
                "sort_order": 1,
                "children": [
                    {"slug": "accounts-payable-receivable", "name_vi": "Công nợ phải thu / phải trả", "name_en": "Accounts Payable / Receivable", "sort_order": 1},
                    {"slug": "tax-accounting", "name_vi": "Kế toán thuế", "name_en": "Tax Accounting", "sort_order": 2},
                    {"slug": "cost-accounting", "name_vi": "Kế toán giá thành", "name_en": "Cost Accounting", "sort_order": 3},
                    {"slug": "payroll-accounting", "name_vi": "Kế toán tiền lương", "name_en": "Payroll Accounting", "sort_order": 4},
                ],
            },
            {
                "slug": "auditing",
                "name_vi": "Kiểm toán",
                "name_en": "Auditing",
                "sort_order": 2,
                "children": [
                    {"slug": "internal-audit", "name_vi": "Kiểm toán nội bộ", "name_en": "Internal Audit", "sort_order": 1},
                    {"slug": "external-audit", "name_vi": "Kiểm toán độc lập", "name_en": "External Audit", "sort_order": 2},
                    {"slug": "it-audit", "name_vi": "Kiểm toán CNTT", "name_en": "IT Audit", "sort_order": 3},
                ],
            },
            {
                "slug": "financial-reporting",
                "name_vi": "Báo cáo tài chính",
                "name_en": "Financial Reporting",
                "sort_order": 3,
                "children": [
                    {"slug": "ifrs-reporting", "name_vi": "Báo cáo IFRS / VAS", "name_en": "IFRS / VAS Reporting", "sort_order": 1},
                    {"slug": "consolidation", "name_vi": "Hợp nhất báo cáo tài chính", "name_en": "Group Consolidation", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 6. Nhân sự (HR)
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "human-resources",
        "name_vi": "Nhân sự (HR)",
        "name_en": "Human Resources",
        "sort_order": 6,
        "children": [
            {
                "slug": "recruitment-talent",
                "name_vi": "Tuyển dụng & Thu hút nhân tài",
                "name_en": "Recruitment & Talent Acquisition",
                "sort_order": 1,
                "children": [
                    {"slug": "technical-recruiter", "name_vi": "Tuyển dụng kỹ thuật", "name_en": "Technical Recruiter", "sort_order": 1},
                    {"slug": "executive-search", "name_vi": "Tuyển dụng cấp cao", "name_en": "Executive Search", "sort_order": 2},
                    {"slug": "campus-recruitment", "name_vi": "Tuyển dụng sinh viên / Graduate", "name_en": "Campus / Graduate Recruitment", "sort_order": 3},
                ],
            },
            {
                "slug": "learning-development",
                "name_vi": "Đào tạo & Phát triển (L&D)",
                "name_en": "Learning & Development",
                "sort_order": 2,
                "children": [
                    {"slug": "training-design", "name_vi": "Thiết kế chương trình đào tạo", "name_en": "Training Design", "sort_order": 1},
                    {"slug": "leadership-development", "name_vi": "Phát triển lãnh đạo", "name_en": "Leadership Development", "sort_order": 2},
                ],
            },
            {
                "slug": "compensation-benefits",
                "name_vi": "Lương thưởng & Phúc lợi (C&B)",
                "name_en": "Compensation & Benefits",
                "sort_order": 3,
                "children": [
                    {"slug": "total-rewards", "name_vi": "Thiết kế chính sách đãi ngộ", "name_en": "Total Rewards Design", "sort_order": 1},
                    {"slug": "benefits-administration", "name_vi": "Quản trị phúc lợi", "name_en": "Benefits Administration", "sort_order": 2},
                ],
            },
            {
                "slug": "hr-business-partner",
                "name_vi": "HR Business Partner (HRBP)",
                "name_en": "HR Business Partner",
                "sort_order": 4,
                "children": [],
            },
            {
                "slug": "hr-operations",
                "name_vi": "Vận hành HR / Hành chính nhân sự",
                "name_en": "HR Operations / Personnel Admin",
                "sort_order": 5,
                "children": [
                    {"slug": "labor-relations", "name_vi": "Quan hệ lao động", "name_en": "Labor Relations", "sort_order": 1},
                    {"slug": "hr-compliance", "name_vi": "Tuân thủ pháp luật lao động", "name_en": "HR Compliance", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 7. Hành chính / Văn phòng
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "administration-office",
        "name_vi": "Hành chính / Văn phòng",
        "name_en": "Administration / Office",
        "sort_order": 7,
        "children": [
            {
                "slug": "executive-assistant",
                "name_vi": "Trợ lý / Thư ký điều hành",
                "name_en": "Executive Assistant / Secretary",
                "sort_order": 1,
                "children": [
                    {"slug": "personal-assistant", "name_vi": "Trợ lý cá nhân", "name_en": "Personal Assistant", "sort_order": 1},
                    {"slug": "office-manager", "name_vi": "Quản lý văn phòng", "name_en": "Office Manager", "sort_order": 2},
                ],
            },
            {
                "slug": "general-admin",
                "name_vi": "Hành chính tổng hợp",
                "name_en": "General Administration",
                "sort_order": 2,
                "children": [
                    {"slug": "receptionist", "name_vi": "Lễ tân / Tiếp tân", "name_en": "Receptionist / Front Desk", "sort_order": 1},
                    {"slug": "document-control", "name_vi": "Quản lý hồ sơ tài liệu", "name_en": "Document Control", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 8. Kỹ thuật / Cơ khí / Ô tô
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "engineering-mechanics",
        "name_vi": "Kỹ thuật / Cơ khí / Ô tô",
        "name_en": "Engineering / Mechanics / Automotive",
        "sort_order": 8,
        "children": [
            {
                "slug": "mechanical-engineering",
                "name_vi": "Kỹ thuật cơ khí",
                "name_en": "Mechanical Engineering",
                "sort_order": 1,
                "children": [
                    {"slug": "manufacturing-engineering", "name_vi": "Kỹ thuật sản xuất / công nghệ chế tạo", "name_en": "Manufacturing / Process Engineering", "sort_order": 1},
                    {"slug": "cad-design", "name_vi": "Thiết kế CAD / mô phỏng", "name_en": "CAD Design / Simulation", "sort_order": 2},
                    {"slug": "tooling-mold", "name_vi": "Khuôn mẫu / dụng cụ", "name_en": "Tooling & Mold", "sort_order": 3},
                    {"slug": "maintenance-engineering", "name_vi": "Kỹ thuật bảo trì", "name_en": "Maintenance Engineering", "sort_order": 4},
                ],
            },
            {
                "slug": "automotive",
                "name_vi": "Kỹ thuật ô tô",
                "name_en": "Automotive Engineering",
                "sort_order": 2,
                "children": [
                    {"slug": "automotive-design", "name_vi": "Thiết kế ô tô", "name_en": "Automotive Design", "sort_order": 1},
                    {"slug": "ev-technology", "name_vi": "Công nghệ xe điện (EV)", "name_en": "EV Technology", "sort_order": 2},
                    {"slug": "automotive-aftersales", "name_vi": "Dịch vụ sau bán hàng ô tô", "name_en": "Automotive Aftersales", "sort_order": 3},
                ],
            },
            {
                "slug": "industrial-engineering",
                "name_vi": "Kỹ thuật công nghiệp / Quản lý sản xuất",
                "name_en": "Industrial Engineering",
                "sort_order": 3,
                "children": [
                    {"slug": "lean-manufacturing", "name_vi": "Lean / Kaizen / 5S", "name_en": "Lean / Kaizen / 5S", "sort_order": 1},
                    {"slug": "quality-engineering", "name_vi": "Kỹ thuật chất lượng (QA/QC)", "name_en": "Quality Engineering (QA/QC)", "sort_order": 2},
                    {"slug": "supply-chain-engineering", "name_vi": "Kỹ thuật chuỗi cung ứng", "name_en": "Supply Chain Engineering", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 9. Điện / Điện tử / Viễn thông
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "electrical-electronics-telecom",
        "name_vi": "Điện / Điện tử / Viễn thông",
        "name_en": "Electrical / Electronics / Telecom",
        "sort_order": 9,
        "children": [
            {
                "slug": "electrical-engineering",
                "name_vi": "Kỹ thuật điện",
                "name_en": "Electrical Engineering",
                "sort_order": 1,
                "children": [
                    {"slug": "power-systems", "name_vi": "Hệ thống điện / Điện lực", "name_en": "Power Systems", "sort_order": 1},
                    {"slug": "electrical-installation", "name_vi": "Thi công lắp đặt điện", "name_en": "Electrical Installation", "sort_order": 2},
                ],
            },
            {
                "slug": "electronics-engineering",
                "name_vi": "Kỹ thuật điện tử",
                "name_en": "Electronics Engineering",
                "sort_order": 2,
                "children": [
                    {"slug": "pcb-hardware-design", "name_vi": "Thiết kế PCB / phần cứng", "name_en": "PCB / Hardware Design", "sort_order": 1},
                    {"slug": "firmware-development", "name_vi": "Lập trình firmware", "name_en": "Firmware Development", "sort_order": 2},
                    {"slug": "iot-engineering", "name_vi": "Kỹ thuật IoT", "name_en": "IoT Engineering", "sort_order": 3},
                ],
            },
            {
                "slug": "telecommunications",
                "name_vi": "Viễn thông",
                "name_en": "Telecommunications",
                "sort_order": 3,
                "children": [
                    {"slug": "telecom-network", "name_vi": "Mạng viễn thông", "name_en": "Telecom Network", "sort_order": 1},
                    {"slug": "5g-mobile-networks", "name_vi": "Mạng di động 4G/5G", "name_en": "4G / 5G Mobile Networks", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 10. Sản xuất / Vận hành
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "manufacturing-operations",
        "name_vi": "Sản xuất / Vận hành",
        "name_en": "Manufacturing / Operations",
        "sort_order": 10,
        "children": [
            {
                "slug": "production-planning",
                "name_vi": "Kế hoạch & điều độ sản xuất",
                "name_en": "Production Planning",
                "sort_order": 1,
                "children": [
                    {"slug": "mrp-erp", "name_vi": "MRP / ERP Sản xuất", "name_en": "MRP / ERP (Manufacturing)", "sort_order": 1},
                    {"slug": "scheduling-control", "name_vi": "Lập lịch & kiểm soát sản xuất", "name_en": "Scheduling & Production Control", "sort_order": 2},
                ],
            },
            {
                "slug": "factory-operations",
                "name_vi": "Vận hành nhà máy",
                "name_en": "Factory Operations",
                "sort_order": 2,
                "children": [
                    {"slug": "shift-supervisor", "name_vi": "Giám sát ca sản xuất", "name_en": "Production Shift Supervisor", "sort_order": 1},
                    {"slug": "plant-manager", "name_vi": "Quản lý nhà máy", "name_en": "Plant Manager", "sort_order": 2},
                ],
            },
            {
                "slug": "quality-control-manufacturing",
                "name_vi": "Kiểm soát chất lượng sản xuất",
                "name_en": "Quality Control (Manufacturing)",
                "sort_order": 3,
                "children": [
                    {"slug": "incoming-quality-control", "name_vi": "Kiểm tra đầu vào (IQC)", "name_en": "Incoming Quality Control (IQC)", "sort_order": 1},
                    {"slug": "outgoing-quality-control", "name_vi": "Kiểm tra đầu ra (OQC)", "name_en": "Outgoing Quality Control (OQC)", "sort_order": 2},
                    {"slug": "iso-certification", "name_vi": "ISO / Tiêu chuẩn chất lượng", "name_en": "ISO / Quality Standards", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 11. Xây dựng / Kiến trúc / Bất động sản
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "construction-architecture-real-estate",
        "name_vi": "Xây dựng / Kiến trúc / Bất động sản",
        "name_en": "Construction / Architecture / Real Estate",
        "sort_order": 11,
        "children": [
            {
                "slug": "architecture-design",
                "name_vi": "Kiến trúc & Thiết kế công trình",
                "name_en": "Architecture & Building Design",
                "sort_order": 1,
                "children": [
                    {"slug": "architectural-design", "name_vi": "Thiết kế kiến trúc", "name_en": "Architectural Design", "sort_order": 1},
                    {"slug": "interior-design-construction", "name_vi": "Thiết kế nội thất công trình", "name_en": "Interior Design (Construction)", "sort_order": 2},
                    {"slug": "landscape-design", "name_vi": "Thiết kế cảnh quan", "name_en": "Landscape Design", "sort_order": 3},
                ],
            },
            {
                "slug": "civil-structural-engineering",
                "name_vi": "Kỹ thuật xây dựng & Kết cấu",
                "name_en": "Civil & Structural Engineering",
                "sort_order": 2,
                "children": [
                    {"slug": "site-supervision", "name_vi": "Giám sát thi công", "name_en": "Site Supervision", "sort_order": 1},
                    {"slug": "quantity-surveying", "name_vi": "Dự toán công trình (QS)", "name_en": "Quantity Surveying (QS)", "sort_order": 2},
                    {"slug": "mep-engineering", "name_vi": "Kỹ thuật MEP (Cơ điện)", "name_en": "MEP Engineering", "sort_order": 3},
                ],
            },
            {
                "slug": "real-estate",
                "name_vi": "Bất động sản",
                "name_en": "Real Estate",
                "sort_order": 3,
                "children": [
                    {"slug": "real-estate-sales", "name_vi": "Môi giới / Kinh doanh BĐS", "name_en": "Real Estate Sales / Brokerage", "sort_order": 1},
                    {"slug": "real-estate-development", "name_vi": "Phát triển dự án BĐS", "name_en": "Real Estate Development", "sort_order": 2},
                    {"slug": "property-management", "name_vi": "Quản lý vận hành tòa nhà", "name_en": "Property Management", "sort_order": 3},
                    {"slug": "real-estate-valuation", "name_vi": "Thẩm định giá BĐS", "name_en": "Real Estate Valuation", "sort_order": 4},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 12. Giáo dục / Đào tạo
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "education-training",
        "name_vi": "Giáo dục / Đào tạo",
        "name_en": "Education / Training",
        "sort_order": 12,
        "children": [
            {
                "slug": "teaching",
                "name_vi": "Giảng dạy",
                "name_en": "Teaching",
                "sort_order": 1,
                "children": [
                    {"slug": "k12-teaching", "name_vi": "Giảng dạy phổ thông (K-12)", "name_en": "K-12 Teaching", "sort_order": 1},
                    {"slug": "higher-education", "name_vi": "Giảng dạy đại học / cao đẳng", "name_en": "Higher Education", "sort_order": 2},
                    {"slug": "language-teaching", "name_vi": "Giảng dạy ngoại ngữ", "name_en": "Language Teaching", "sort_order": 3},
                    {"slug": "corporate-training", "name_vi": "Đào tạo doanh nghiệp", "name_en": "Corporate Training", "sort_order": 4},
                ],
            },
            {
                "slug": "education-administration",
                "name_vi": "Quản lý giáo dục",
                "name_en": "Education Administration",
                "sort_order": 2,
                "children": [
                    {"slug": "curriculum-development", "name_vi": "Phát triển chương trình học", "name_en": "Curriculum Development", "sort_order": 1},
                    {"slug": "academic-affairs", "name_vi": "Công tác học vụ", "name_en": "Academic Affairs", "sort_order": 2},
                    {"slug": "student-affairs", "name_vi": "Công tác sinh viên", "name_en": "Student Affairs", "sort_order": 3},
                ],
            },
            {
                "slug": "edtech",
                "name_vi": "Công nghệ giáo dục (EdTech)",
                "name_en": "EdTech",
                "sort_order": 3,
                "children": [
                    {"slug": "elearning-development", "name_vi": "Phát triển nội dung e-learning", "name_en": "E-learning Content Development", "sort_order": 1},
                    {"slug": "instructional-design", "name_vi": "Thiết kế học liệu", "name_en": "Instructional Design", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 13. Y tế / Dược phẩm / Sức khỏe
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "healthcare-pharma",
        "name_vi": "Y tế / Dược phẩm / Sức khỏe",
        "name_en": "Healthcare / Pharmaceutical / Health",
        "sort_order": 13,
        "children": [
            {
                "slug": "clinical-healthcare",
                "name_vi": "Y tế lâm sàng",
                "name_en": "Clinical Healthcare",
                "sort_order": 1,
                "children": [
                    {"slug": "medical-doctor", "name_vi": "Bác sĩ", "name_en": "Medical Doctor", "sort_order": 1},
                    {"slug": "nursing", "name_vi": "Điều dưỡng / Y tá", "name_en": "Nursing", "sort_order": 2},
                    {"slug": "medical-laboratory", "name_vi": "Xét nghiệm y tế", "name_en": "Medical Laboratory", "sort_order": 3},
                    {"slug": "physiotherapy", "name_vi": "Vật lý trị liệu", "name_en": "Physiotherapy", "sort_order": 4},
                ],
            },
            {
                "slug": "pharmaceutical",
                "name_vi": "Dược phẩm",
                "name_en": "Pharmaceutical",
                "sort_order": 2,
                "children": [
                    {"slug": "medical-representative", "name_vi": "Trình dược viên (MR)", "name_en": "Medical Representative (MR)", "sort_order": 1},
                    {"slug": "pharmaceutical-rd", "name_vi": "Nghiên cứu & phát triển dược", "name_en": "Pharmaceutical R&D", "sort_order": 2},
                    {"slug": "regulatory-affairs-pharma", "name_vi": "Đăng ký / Pháp chế dược", "name_en": "Regulatory Affairs (Pharma)", "sort_order": 3},
                    {"slug": "pharmacist", "name_vi": "Dược sĩ", "name_en": "Pharmacist", "sort_order": 4},
                ],
            },
            {
                "slug": "healthcare-management",
                "name_vi": "Quản lý y tế & Chăm sóc sức khỏe",
                "name_en": "Healthcare Management",
                "sort_order": 3,
                "children": [
                    {"slug": "hospital-administration", "name_vi": "Quản trị bệnh viện", "name_en": "Hospital Administration", "sort_order": 1},
                    {"slug": "health-insurance-mgmt", "name_vi": "Quản lý bảo hiểm y tế", "name_en": "Health Insurance Management", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 14. Logistics / Xuất nhập khẩu / Vận tải
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "logistics-import-export",
        "name_vi": "Logistics / Xuất nhập khẩu / Vận tải",
        "name_en": "Logistics / Import-Export / Transportation",
        "sort_order": 14,
        "children": [
            {
                "slug": "supply-chain-management",
                "name_vi": "Quản lý chuỗi cung ứng",
                "name_en": "Supply Chain Management",
                "sort_order": 1,
                "children": [
                    {"slug": "procurement-purchasing", "name_vi": "Mua hàng / Thu mua", "name_en": "Procurement / Purchasing", "sort_order": 1},
                    {"slug": "inventory-warehouse", "name_vi": "Kho bãi / Quản lý tồn kho", "name_en": "Warehouse & Inventory", "sort_order": 2},
                    {"slug": "demand-planning", "name_vi": "Dự báo & Kế hoạch nhu cầu", "name_en": "Demand Planning", "sort_order": 3},
                ],
            },
            {
                "slug": "freight-forwarding",
                "name_vi": "Giao nhận hàng hóa (Freight)",
                "name_en": "Freight Forwarding",
                "sort_order": 2,
                "children": [
                    {"slug": "sea-freight", "name_vi": "Vận tải đường biển", "name_en": "Sea Freight", "sort_order": 1},
                    {"slug": "air-freight", "name_vi": "Vận tải hàng không", "name_en": "Air Freight", "sort_order": 2},
                    {"slug": "customs-clearance", "name_vi": "Thủ tục hải quan", "name_en": "Customs Clearance", "sort_order": 3},
                ],
            },
            {
                "slug": "import-export",
                "name_vi": "Xuất nhập khẩu",
                "name_en": "Import / Export",
                "sort_order": 3,
                "children": [
                    {"slug": "export-documentation", "name_vi": "Chứng từ xuất nhập khẩu", "name_en": "Export Documentation", "sort_order": 1},
                    {"slug": "trade-compliance", "name_vi": "Tuân thủ thương mại quốc tế", "name_en": "Trade Compliance", "sort_order": 2},
                ],
            },
            {
                "slug": "transportation",
                "name_vi": "Vận tải",
                "name_en": "Transportation",
                "sort_order": 4,
                "children": [
                    {"slug": "fleet-management", "name_vi": "Quản lý phương tiện", "name_en": "Fleet Management", "sort_order": 1},
                    {"slug": "last-mile-delivery", "name_vi": "Giao hàng chặng cuối", "name_en": "Last-mile Delivery", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 15. Du lịch / Khách sạn / F&B
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "tourism-hospitality-fnb",
        "name_vi": "Du lịch / Khách sạn / Nhà hàng (F&B)",
        "name_en": "Tourism / Hospitality / F&B",
        "sort_order": 15,
        "children": [
            {
                "slug": "hotel-resort",
                "name_vi": "Khách sạn / Khu nghỉ dưỡng",
                "name_en": "Hotel & Resort",
                "sort_order": 1,
                "children": [
                    {"slug": "front-office", "name_vi": "Lễ tân / Front Office", "name_en": "Front Office", "sort_order": 1},
                    {"slug": "housekeeping", "name_vi": "Buồng phòng (Housekeeping)", "name_en": "Housekeeping", "sort_order": 2},
                    {"slug": "hotel-management", "name_vi": "Quản lý khách sạn", "name_en": "Hotel Management", "sort_order": 3},
                    {"slug": "revenue-management", "name_vi": "Quản lý doanh thu (Revenue)", "name_en": "Revenue Management", "sort_order": 4},
                ],
            },
            {
                "slug": "food-beverage",
                "name_vi": "Ẩm thực & Đồ uống (F&B)",
                "name_en": "Food & Beverage (F&B)",
                "sort_order": 2,
                "children": [
                    {"slug": "chef-kitchen", "name_vi": "Đầu bếp / Bếp trưởng", "name_en": "Chef / Kitchen", "sort_order": 1},
                    {"slug": "restaurant-service", "name_vi": "Phục vụ nhà hàng", "name_en": "Restaurant Service", "sort_order": 2},
                    {"slug": "fnb-management", "name_vi": "Quản lý F&B", "name_en": "F&B Management", "sort_order": 3},
                    {"slug": "barista-bartender", "name_vi": "Barista / Bartender", "name_en": "Barista / Bartender", "sort_order": 4},
                ],
            },
            {
                "slug": "travel-tourism",
                "name_vi": "Du lịch & Lữ hành",
                "name_en": "Travel & Tourism",
                "sort_order": 3,
                "children": [
                    {"slug": "tour-guide", "name_vi": "Hướng dẫn viên du lịch", "name_en": "Tour Guide", "sort_order": 1},
                    {"slug": "travel-agency", "name_vi": "Đại lý lữ hành", "name_en": "Travel Agency", "sort_order": 2},
                    {"slug": "destination-management", "name_vi": "Quản lý điểm đến (DMC)", "name_en": "Destination Management (DMC)", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 16. Thiết kế / Sáng tạo
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "design-creative",
        "name_vi": "Thiết kế / Sáng tạo",
        "name_en": "Design / Creative",
        "sort_order": 16,
        "children": [
            {
                "slug": "ui-ux-design",
                "name_vi": "Thiết kế UI/UX",
                "name_en": "UI / UX Design",
                "sort_order": 1,
                "children": [
                    {"slug": "ux-research", "name_vi": "Nghiên cứu trải nghiệm người dùng (UX Research)", "name_en": "UX Research", "sort_order": 1},
                    {"slug": "product-design", "name_vi": "Thiết kế sản phẩm số", "name_en": "Product Design", "sort_order": 2},
                    {"slug": "interaction-design", "name_vi": "Thiết kế tương tác (IxD)", "name_en": "Interaction Design (IxD)", "sort_order": 3},
                ],
            },
            {
                "slug": "graphic-design",
                "name_vi": "Thiết kế đồ họa",
                "name_en": "Graphic Design",
                "sort_order": 2,
                "children": [
                    {"slug": "visual-design", "name_vi": "Thiết kế trực quan / nhận diện thương hiệu", "name_en": "Visual / Brand Identity Design", "sort_order": 1},
                    {"slug": "print-publishing-design", "name_vi": "Thiết kế ấn phẩm / xuất bản", "name_en": "Print & Publishing Design", "sort_order": 2},
                    {"slug": "packaging-design", "name_vi": "Thiết kế bao bì", "name_en": "Packaging Design", "sort_order": 3},
                ],
            },
            {
                "slug": "motion-video",
                "name_vi": "Motion / Video / Hoạt hình",
                "name_en": "Motion / Video / Animation",
                "sort_order": 3,
                "children": [
                    {"slug": "motion-graphics", "name_vi": "Motion Graphics", "name_en": "Motion Graphics", "sort_order": 1},
                    {"slug": "video-production", "name_vi": "Sản xuất video", "name_en": "Video Production", "sort_order": 2},
                    {"slug": "3d-animation", "name_vi": "Hoạt hình 3D / VFX", "name_en": "3D Animation / VFX", "sort_order": 3},
                ],
            },
            {
                "slug": "fashion-textile-design",
                "name_vi": "Thời trang / Dệt may",
                "name_en": "Fashion / Textile Design",
                "sort_order": 4,
                "children": [
                    {"slug": "fashion-design", "name_vi": "Thiết kế thời trang", "name_en": "Fashion Design", "sort_order": 1},
                    {"slug": "textile-pattern", "name_vi": "Thiết kế dệt / in hoa", "name_en": "Textile & Pattern Design", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 17. Truyền thông / Báo chí / Xuất bản
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "media-journalism",
        "name_vi": "Truyền thông / Báo chí / Xuất bản",
        "name_en": "Media / Journalism / Publishing",
        "sort_order": 17,
        "children": [
            {
                "slug": "journalism-reporting",
                "name_vi": "Báo chí / Phóng sự",
                "name_en": "Journalism / Reporting",
                "sort_order": 1,
                "children": [
                    {"slug": "news-reporting", "name_vi": "Phóng viên tin tức", "name_en": "News Reporter", "sort_order": 1},
                    {"slug": "investigative-journalism", "name_vi": "Báo chí điều tra", "name_en": "Investigative Journalism", "sort_order": 2},
                    {"slug": "broadcast-journalism", "name_vi": "Báo chí phát thanh / truyền hình", "name_en": "Broadcast Journalism", "sort_order": 3},
                ],
            },
            {
                "slug": "content-creation",
                "name_vi": "Sản xuất nội dung",
                "name_en": "Content Creation",
                "sort_order": 2,
                "children": [
                    {"slug": "copywriting", "name_vi": "Viết quảng cáo / Copywriting", "name_en": "Copywriting", "sort_order": 1},
                    {"slug": "editorial", "name_vi": "Biên tập / Xuất bản", "name_en": "Editorial / Publishing", "sort_order": 2},
                    {"slug": "social-content-creator", "name_vi": "Sáng tạo nội dung mạng xã hội", "name_en": "Social Media Content Creator", "sort_order": 3},
                    {"slug": "podcast-radio", "name_vi": "Podcast / Radio", "name_en": "Podcast / Radio", "sort_order": 4},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 18. Pháp lý
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "legal",
        "name_vi": "Pháp lý / Luật",
        "name_en": "Legal",
        "sort_order": 18,
        "children": [
            {
                "slug": "corporate-legal",
                "name_vi": "Pháp chế doanh nghiệp",
                "name_en": "Corporate Legal",
                "sort_order": 1,
                "children": [
                    {"slug": "legal-counsel", "name_vi": "Luật sư / Cố vấn pháp lý nội bộ", "name_en": "In-house Legal Counsel", "sort_order": 1},
                    {"slug": "contract-management", "name_vi": "Quản lý hợp đồng", "name_en": "Contract Management", "sort_order": 2},
                    {"slug": "compliance-legal", "name_vi": "Tuân thủ pháp lý / Compliance", "name_en": "Legal Compliance", "sort_order": 3},
                ],
            },
            {
                "slug": "law-practice",
                "name_vi": "Hành nghề luật",
                "name_en": "Law Practice",
                "sort_order": 2,
                "children": [
                    {"slug": "litigation", "name_vi": "Tranh tụng / Tố tụng", "name_en": "Litigation", "sort_order": 1},
                    {"slug": "intellectual-property", "name_vi": "Sở hữu trí tuệ (IP)", "name_en": "Intellectual Property (IP)", "sort_order": 2},
                    {"slug": "tax-law", "name_vi": "Luật thuế", "name_en": "Tax Law", "sort_order": 3},
                    {"slug": "labor-law", "name_vi": "Luật lao động", "name_en": "Labor Law", "sort_order": 4},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 19. Khoa học / Nghiên cứu
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "science-research",
        "name_vi": "Khoa học / Nghiên cứu",
        "name_en": "Science / Research",
        "sort_order": 19,
        "children": [
            {
                "slug": "natural-sciences",
                "name_vi": "Khoa học tự nhiên",
                "name_en": "Natural Sciences",
                "sort_order": 1,
                "children": [
                    {"slug": "chemistry", "name_vi": "Hóa học", "name_en": "Chemistry", "sort_order": 1},
                    {"slug": "physics", "name_vi": "Vật lý", "name_en": "Physics", "sort_order": 2},
                    {"slug": "biology-life-sciences", "name_vi": "Sinh học / Khoa học đời sống", "name_en": "Biology / Life Sciences", "sort_order": 3},
                    {"slug": "environmental-science", "name_vi": "Khoa học môi trường", "name_en": "Environmental Science", "sort_order": 4},
                ],
            },
            {
                "slug": "applied-research",
                "name_vi": "Nghiên cứu ứng dụng",
                "name_en": "Applied Research",
                "sort_order": 2,
                "children": [
                    {"slug": "materials-science", "name_vi": "Khoa học vật liệu", "name_en": "Materials Science", "sort_order": 1},
                    {"slug": "biomedical-research", "name_vi": "Nghiên cứu y sinh", "name_en": "Biomedical Research", "sort_order": 2},
                    {"slug": "food-technology-research", "name_vi": "Công nghệ thực phẩm", "name_en": "Food Technology", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 20. Nông nghiệp / Lâm nghiệp / Thủy sản
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "agriculture-forestry-fishery",
        "name_vi": "Nông nghiệp / Lâm nghiệp / Thủy sản",
        "name_en": "Agriculture / Forestry / Fishery",
        "sort_order": 20,
        "children": [
            {
                "slug": "agronomy",
                "name_vi": "Trồng trọt / Nông học",
                "name_en": "Agronomy / Crop Science",
                "sort_order": 1,
                "children": [
                    {"slug": "precision-agriculture", "name_vi": "Nông nghiệp chính xác / công nghệ cao", "name_en": "Precision / High-tech Agriculture", "sort_order": 1},
                    {"slug": "plant-protection", "name_vi": "Bảo vệ thực vật", "name_en": "Plant Protection", "sort_order": 2},
                ],
            },
            {
                "slug": "aquaculture",
                "name_vi": "Nuôi trồng thủy sản",
                "name_en": "Aquaculture / Fishery",
                "sort_order": 2,
                "children": [
                    {"slug": "aquatic-farming", "name_vi": "Nuôi trồng thủy sản", "name_en": "Aquatic Farming", "sort_order": 1},
                    {"slug": "fisheries-management", "name_vi": "Quản lý nguồn lợi thủy sản", "name_en": "Fisheries Management", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 21. Môi trường / Năng lượng
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "environment-energy",
        "name_vi": "Môi trường / Năng lượng",
        "name_en": "Environment / Energy",
        "sort_order": 21,
        "children": [
            {
                "slug": "renewable-energy",
                "name_vi": "Năng lượng tái tạo",
                "name_en": "Renewable Energy",
                "sort_order": 1,
                "children": [
                    {"slug": "solar-energy", "name_vi": "Năng lượng mặt trời", "name_en": "Solar Energy", "sort_order": 1},
                    {"slug": "wind-energy", "name_vi": "Năng lượng gió", "name_en": "Wind Energy", "sort_order": 2},
                    {"slug": "energy-storage", "name_vi": "Lưu trữ năng lượng", "name_en": "Energy Storage", "sort_order": 3},
                ],
            },
            {
                "slug": "environmental-management",
                "name_vi": "Quản lý môi trường",
                "name_en": "Environmental Management",
                "sort_order": 2,
                "children": [
                    {"slug": "esg-sustainability", "name_vi": "ESG / Phát triển bền vững", "name_en": "ESG / Sustainability", "sort_order": 1},
                    {"slug": "waste-management", "name_vi": "Quản lý chất thải", "name_en": "Waste Management", "sort_order": 2},
                    {"slug": "environmental-compliance", "name_vi": "Tuân thủ môi trường", "name_en": "Environmental Compliance", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 22. Dịch vụ khách hàng
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "customer-service",
        "name_vi": "Dịch vụ khách hàng",
        "name_en": "Customer Service",
        "sort_order": 22,
        "children": [
            {
                "slug": "call-center",
                "name_vi": "Trung tâm hỗ trợ khách hàng (Call Center)",
                "name_en": "Call Center / Contact Center",
                "sort_order": 1,
                "children": [
                    {"slug": "inbound-support", "name_vi": "Hỗ trợ đầu vào (Inbound)", "name_en": "Inbound Support", "sort_order": 1},
                    {"slug": "outbound-support", "name_vi": "Hỗ trợ đầu ra / Outbound", "name_en": "Outbound Support", "sort_order": 2},
                    {"slug": "technical-support", "name_vi": "Hỗ trợ kỹ thuật", "name_en": "Technical Support", "sort_order": 3},
                ],
            },
            {
                "slug": "customer-success",
                "name_vi": "Thành công khách hàng (Customer Success)",
                "name_en": "Customer Success",
                "sort_order": 2,
                "children": [
                    {"slug": "account-management-cs", "name_vi": "Quản lý tài khoản khách hàng", "name_en": "Account Management (CS)", "sort_order": 1},
                    {"slug": "onboarding-specialist", "name_vi": "Chuyên viên hỗ trợ khởi đầu", "name_en": "Onboarding Specialist", "sort_order": 2},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 23. Bán lẻ / Hàng tiêu dùng (FMCG)
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "retail-consumer-goods",
        "name_vi": "Bán lẻ / Hàng tiêu dùng (FMCG)",
        "name_en": "Retail / Consumer Goods (FMCG)",
        "sort_order": 23,
        "children": [
            {
                "slug": "fmcg-trade",
                "name_vi": "FMCG & Thương mại",
                "name_en": "FMCG & Trade",
                "sort_order": 1,
                "children": [
                    {"slug": "trade-marketing", "name_vi": "Trade Marketing", "name_en": "Trade Marketing", "sort_order": 1},
                    {"slug": "category-management", "name_vi": "Quản lý ngành hàng", "name_en": "Category Management", "sort_order": 2},
                    {"slug": "modern-trade", "name_vi": "Kênh hiện đại (MT / MT Sales)", "name_en": "Modern Trade (MT)", "sort_order": 3},
                    {"slug": "general-trade", "name_vi": "Kênh truyền thống (GT)", "name_en": "General Trade (GT)", "sort_order": 4},
                ],
            },
            {
                "slug": "retail-operations",
                "name_vi": "Vận hành bán lẻ",
                "name_en": "Retail Operations",
                "sort_order": 2,
                "children": [
                    {"slug": "store-management", "name_vi": "Quản lý cửa hàng", "name_en": "Store Management", "sort_order": 1},
                    {"slug": "visual-merchandising", "name_vi": "Trưng bày hàng hóa (Visual Merchandising)", "name_en": "Visual Merchandising", "sort_order": 2},
                    {"slug": "ecommerce-operations", "name_vi": "Vận hành thương mại điện tử", "name_en": "E-commerce Operations", "sort_order": 3},
                ],
            },
        ],
    },

    # ════════════════════════════════════════════════════════════════════════
    # 24. Tư vấn / Quản lý chiến lược
    # ════════════════════════════════════════════════════════════════════════
    {
        "slug": "consulting-management",
        "name_vi": "Tư vấn / Quản lý chiến lược",
        "name_en": "Consulting / Strategy Management",
        "sort_order": 24,
        "children": [
            {
                "slug": "management-consulting",
                "name_vi": "Tư vấn quản lý",
                "name_en": "Management Consulting",
                "sort_order": 1,
                "children": [
                    {"slug": "strategy-consulting", "name_vi": "Tư vấn chiến lược", "name_en": "Strategy Consulting", "sort_order": 1},
                    {"slug": "operations-consulting", "name_vi": "Tư vấn vận hành", "name_en": "Operations Consulting", "sort_order": 2},
                    {"slug": "digital-transformation", "name_vi": "Tư vấn chuyển đổi số", "name_en": "Digital Transformation Consulting", "sort_order": 3},
                ],
            },
            {
                "slug": "it-consulting",
                "name_vi": "Tư vấn CNTT",
                "name_en": "IT Consulting",
                "sort_order": 2,
                "children": [
                    {"slug": "erp-consulting", "name_vi": "Tư vấn ERP (SAP / Oracle)", "name_en": "ERP Consulting (SAP / Oracle)", "sort_order": 1},
                    {"slug": "technology-advisory", "name_vi": "Tư vấn công nghệ doanh nghiệp", "name_en": "Technology Advisory", "sort_order": 2},
                ],
            },
        ],
    },
]
