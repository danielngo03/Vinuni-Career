"""Tech/industry term expansion for CV-JD semantic matching.

Two complementary expansion layers:

1. **Synonym expansion** (bidirectional, token-based)
   ``_EXPANSION_MAP`` maps canonical form → aliases that are pure spelling/
   shorthand variants of the SAME technology.
   Example: "k8s" ↔ "kubernetes" — different spellings of one product.

2. **Implication expansion** (one-way, substring-based, CV-side only)
   ``_CV_IMPLIES_MAP`` maps a skill found in a CV to a list of prerequisite
   skills it implies the candidate also knows. The implied skills are appended
   to the expanded CV text so that JD requirements can match them — but the
   JD terms themselves are NEVER expanded with implications, preserving correct
   gap detection.
   Example: "Node.js" in CV → implies "JavaScript" knowledge, so a JD
   requirement of "JavaScript" is satisfied. But "JavaScript" in CV does NOT
   satisfy a JD requirement of "Node.js" (browser JS ≠ Node.js backend dev).

``expand_text(cv_text)`` enriches CV text with both synonym expansions AND
implied skills (CV → JD direction only).

``term_matches(jd_term, expanded_cv_text)`` expands the JD term using synonyms
only, then checks substring containment in the already-enriched CV text. This
ensures k8s↔kubernetes is bidirectional while fastapi/python directionality
is preserved.
"""

from __future__ import annotations

import re
from functools import lru_cache

# ---------------------------------------------------------------------------
# 1. Bidirectional synonym map (pure spelling / shorthand variants)
#    Keys are lowercase canonical tokens. Values are additional lowercase forms
#    that should match the same skill. Expansion is symmetric: if "k8s" is in
#    the CV, "kubernetes" is appended; if "kubernetes" is in the CV, "k8s" is
#    appended.
# ---------------------------------------------------------------------------

_EXPANSION_MAP: dict[str, list[str]] = {
    # ── Cloud & Infrastructure ──────────────────────────────────────────────
    "kubernetes": ["k8s", "kube"],
    "docker": ["containerization", "containers"],
    "terraform": ["iac", "infrastructure as code"],
    "ansible": ["configuration management"],
    "aws": [
        "amazon web services",
        "amazon cloud",
        "ec2",
        "s3",
        "eks",
        "lambda",
        "cloudfront",
        "rds",
    ],
    "gcp": ["google cloud", "google cloud platform", "gke", "bigquery", "cloud run"],
    "azure": ["microsoft azure", "aks", "azure devops", "azure functions"],
    "ci/cd": ["cicd", "continuous integration", "continuous delivery", "continuous deployment",
               "github actions", "gitlab ci", "jenkins", "circle ci", "travis ci", "argocd"],
    "devops": ["dev ops", "site reliability", "sre", "platform engineering"],
    "microservices": ["micro-services", "micro services", "service mesh", "soa"],
    "serverless": ["faas", "function as a service", "lambda", "cloud functions"],
    "linux": ["unix", "ubuntu", "debian", "centos", "rhel", "fedora", "bash", "shell scripting"],
    "nginx": ["web server", "reverse proxy", "load balancer"],
    "redis": ["in-memory cache", "cache", "caching"],
    "kafka": ["apache kafka", "event streaming", "message queue", "message broker"],
    "rabbitmq": ["message broker", "amqp", "event queue"],
    "elasticsearch": ["elk stack", "elastic", "search engine"],
    "prometheus": ["grafana", "monitoring", "observability", "alerting"],
    "datadog": ["monitoring", "apm", "observability"],
    "istio": ["service mesh", "envoy proxy"],

    # ── Programming Languages ───────────────────────────────────────────────
    # ONLY abbreviation/spelling variants here. Framework names are SEPARATE
    # entries (see web frameworks section). This prevents "python" from matching
    # "fastapi" — having Python does NOT mean you know FastAPI (gap detection).
    "python": ["py", "python3", "python 3"],
    "javascript": ["js", "es6", "ecmascript"],
    "typescript": ["ts", "tsx"],
    "node.js": ["nodejs", "node js", "node"],
    "java": ["jvm"],
    "c#": ["csharp"],
    ".net": ["dotnet", "asp.net core"],
    "go": ["golang"],
    "rust": ["cargo"],
    "swift": [],
    "kotlin": [],
    "dart": [],
    "php": [],
    "ruby": [],
    "scala": ["akka"],
    "r": ["r language", "rstudio", "tidyverse"],
    "matlab": ["simulink"],
    "c++": ["cpp"],
    "c": ["c language", "embedded c", "ansi c"],

    # ── Web Frameworks (spelling variants only, no language bridging) ───────
    # NOTE: Language implications go in _CV_IMPLIES_MAP, NOT here.
    "react": ["react.js", "reactjs", "redux"],
    "react native": ["react-native"],
    "vue": ["vue.js", "vuejs"],
    "nuxt": ["nuxt.js"],
    "angular": ["ng", "angularjs"],
    "next.js": ["nextjs"],
    "fastapi": ["fast api"],
    "django": ["django rest framework", "drf"],
    "flask": ["flask api"],
    "spring": ["spring framework", "spring mvc"],
    "spring boot": ["springboot"],
    "express": ["express.js", "expressjs"],
    "laravel": ["laravel php"],
    "rails": ["ruby on rails"],
    "gin": [],
    "fiber": [],
    "actix": [],
    "echo": [],
    "nestjs": ["nest.js"],
    "fastify": [],
    "hapi": [],
    "koa": [],
    "swiftui": [],
    "flutter": [],
    "jetpack compose": [],

    # ── Web & Frontend ──────────────────────────────────────────────────────
    "html": ["html5", "hypertext"],
    "css": ["css3", "sass", "scss", "less", "tailwind", "bootstrap"],
    "graphql": ["gql", "apollo"],
    "rest": ["restful", "rest api", "http api"],
    "grpc": ["protocol buffers", "protobuf"],
    "websocket": ["ws", "socket.io", "real-time"],

    # ── Databases ───────────────────────────────────────────────────────────
    "postgresql": ["postgres", "pg", "psql"],
    "mysql": ["mariadb"],
    "mongodb": ["mongo", "nosql document"],
    "oracle": ["oracle db", "oracle database", "pl/sql", "plsql"],
    "sql server": ["mssql", "microsoft sql", "t-sql", "tsql"],
    "sqlite": ["sqlite3"],
    "cassandra": ["apache cassandra", "nosql wide column"],
    "dynamodb": ["aws dynamodb"],
    "neo4j": ["graph database", "cypher"],
    "clickhouse": ["olap", "columnar database"],
    "snowflake": ["data warehouse", "cloud data warehouse"],
    "bigquery": ["bq", "google bigquery"],
    "redshift": ["aws redshift"],

    # ── Data / ML / AI ──────────────────────────────────────────────────────
    "machine learning": ["ml", "supervised learning", "unsupervised learning", "classification",
                         "regression", "clustering", "random forest", "xgboost", "lightgbm"],
    "deep learning": ["dl", "neural network", "cnn", "rnn", "lstm", "transformer",
                      "convolutional", "recurrent"],
    "artificial intelligence": ["ai", "intelligent systems"],
    "natural language processing": ["nlp", "text mining", "sentiment analysis", "named entity",
                                    "ner", "text classification"],
    "computer vision": ["image recognition", "object detection", "yolo", "opencv"],
    "reinforcement learning": ["rl", "reward learning"],
    "pytorch": ["torch"],
    "tensorflow": ["tf", "keras"],
    "scikit-learn": ["sklearn", "scikit learn"],
    "pandas": ["pd", "dataframe"],
    "numpy": ["np", "numerical python"],
    "data science": ["ds", "data analytics", "data analysis", "business intelligence", "bi"],
    "etl": ["extract transform load", "data pipeline", "data integration"],
    "mlops": ["ml ops", "machine learning operations", "model deployment", "model serving"],
    "llm": ["large language model", "gpt", "language model", "generative ai"],
    "rag": ["retrieval augmented generation", "vector search", "semantic search"],
    "embedding": ["vector embedding", "text embedding", "sentence embedding"],
    "pgvector": ["vector database", "vector store"],
    "apache spark": ["spark", "pyspark", "distributed computing"],
    "apache airflow": ["airflow", "workflow orchestration", "dag"],
    "dbt": ["data build tool", "data transformation"],
    "tableau": ["data visualization", "bi tool", "dashboard"],
    "power bi": ["powerbi", "microsoft power bi", "bi dashboard"],

    # ── DevSecOps / Security ─────────────────────────────────────────────────
    "devsecops": ["dev sec ops", "security engineering", "application security", "appsec"],
    "owasp": ["web application security", "injection", "xss"],
    "sast": ["static analysis", "code scanning", "sonarqube", "semgrep"],
    "dast": ["dynamic analysis", "penetration testing", "owasp zap"],
    "pci-dss": ["pci dss", "payment card security"],
    "iso 27001": ["information security management", "isms"],
    "gdpr": ["data privacy", "data protection"],
    "jwt": ["json web token", "authentication token"],
    "oauth": ["oauth2", "openid connect", "oidc"],
    "zero trust": ["zero-trust", "zero trust security"],
    "vault": ["hashicorp vault", "secrets management"],

    # ── Automotive / Embedded ────────────────────────────────────────────────
    "autosar": ["autosar classic", "autosar adaptive"],
    "can bus": ["can", "can-fd", "automotive bus", "controller area network"],
    "embedded": ["embedded systems", "embedded software", "firmware", "rtos"],
    "freertos": ["real-time os", "real-time operating system"],
    "arm": ["arm cortex", "arm processor", "cortex-m", "cortex-a"],
    "fpga": ["field programmable gate array", "vhdl", "verilog"],
    "iso 26262": ["functional safety", "asil", "automotive safety"],
    "adas": ["advanced driver assistance", "autonomous driving", "self-driving"],
    "bms": ["battery management system", "battery management"],
    "can": ["controller area network", "can bus", "can-fd"],
    "ota": ["over the air update", "firmware update"],

    # ── Finance / Banking ─────────────────────────────────────────────────────
    "cfa": ["chartered financial analyst"],
    "cpa": ["certified public accountant"],
    "frm": ["financial risk manager"],
    "acca": ["association of chartered certified accountants"],
    "aml": ["anti-money laundering"],
    "kyc": ["know your customer"],
    "dcf": ["discounted cash flow", "valuation model"],
    "lbo": ["leveraged buyout"],
    "ipo": ["initial public offering"],
    "esg": ["environmental social governance", "sustainable investing"],
    "fintech": ["financial technology", "payment technology"],
    "swift network": ["swift payment", "bank transfer", "interbank"],
    "api banking": ["open banking", "bank api"],
    "pos": ["point of sale"],
    "payment gateway": ["payment processing", "vnpay", "momo", "zalopay"],
    "trading": ["equity trading", "stock trading", "algorithmic trading", "quant"],

    # ── Healthcare / Life Science ─────────────────────────────────────────────
    "hl7": ["hl7 fhir", "healthcare interoperability", "medical data exchange"],
    "fhir": ["fast healthcare interoperability resources"],
    "his": ["hospital information system"],
    "lis": ["laboratory information system"],
    "pacs": ["picture archiving", "medical imaging"],
    "dicom": ["medical image format"],
    "icd": ["icd-10", "icd-11", "diagnosis coding"],
    "hipaa": ["health data privacy", "patient data protection"],
    "clinical trials": ["gcp", "clinical research", "phase 1", "phase 2", "phase 3"],

    # ── Aviation / Logistics ─────────────────────────────────────────────────
    "gds": ["global distribution system", "amadeus", "sabre", "galileo", "travelport"],
    "ndc": ["new distribution capability", "iata ndc"],
    "iata": ["airline standards", "airline industry"],
    "erp": ["enterprise resource planning", "sap", "oracle erp"],
    "wms": ["warehouse management system"],
    "tms": ["transportation management system"],
    "scm": ["supply chain management"],

    # ── Agile / Project Management ────────────────────────────────────────────
    "scrum": ["agile scrum", "sprint", "daily standup", "retrospective"],
    "kanban": ["agile kanban", "lean"],
    "safe": ["scaled agile framework", "pi planning"],
    "jira": ["project tracking", "issue tracking", "atlassian"],
    "okr": ["objectives and key results", "goal setting"],
    "product management": ["pm", "product owner", "roadmap", "backlog"],
    "ba": ["business analyst", "business analysis", "requirements analysis"],

    # ── Design / UX ──────────────────────────────────────────────────────────
    "figma": ["ui design", "ux design", "prototyping", "wireframing", "design tool"],
    "ux": ["user experience", "usability", "user research", "hci"],
    "ui": ["user interface", "front-end design", "interaction design"],
    "a/b testing": ["ab testing", "experimentation", "conversion optimization"],
    "hig": ["apple human interface guidelines", "ios design guidelines"],
    "material design": ["google material", "material ui", "mui"],

    # ── Vietnamese city aliases — bidirectional so both CV and JD variants match
    "ho chi minh city": [
        "hcmc", "hcm", "saigon", "sài gòn", "sai gon",
        "tp hcm", "tp.hcm", "tp. hồ chí minh", "thành phố hồ chí minh",
    ],
    "hcmc": ["ho chi minh city", "hcm", "saigon", "sài gòn"],
    "hcm": ["ho chi minh city", "hcmc", "saigon"],
    "saigon": ["ho chi minh city", "hcmc", "sài gòn"],
    "sài gòn": ["ho chi minh city", "hcmc", "saigon"],
    "hanoi": ["hà nội", "ha noi", "hn"],
    "hà nội": ["hanoi", "ha noi", "hn"],
    "ha noi": ["hanoi", "hà nội", "hn"],
    "hn": ["hanoi", "hà nội"],
    "da nang": ["đà nẵng"],
    "đà nẵng": ["da nang"],

    # ── Vietnamese-specific ───────────────────────────────────────────────────
    "cntt": ["công nghệ thông tin", "information technology", "it"],
    "ktpm": ["kỹ thuật phần mềm", "software engineering"],
    "khmt": ["khoa học máy tính", "computer science"],
    "httt": ["hệ thống thông tin", "information systems"],
    "attt": ["an toàn thông tin", "information security", "cybersecurity"],
    "kspm": ["kỹ sư phần mềm", "software engineer"],
    "kstt": ["kỹ sư thông tin"],
    "ktkt": ["kỹ thuật kinh tế"],
    "qtkd": ["quản trị kinh doanh", "business administration", "mba"],
    "tckt": ["tài chính kế toán"],
    "nhtm": ["ngân hàng thương mại"],
    "dn": ["doanh nghiệp"],
    "ktvm": ["kinh tế vĩ mô"],
    "ktvi": ["kinh tế vi mô"],
    "khtn": ["khoa học tự nhiên"],

    # ── Role abbreviations (bidirectional) ───────────────────────────────────
    "pm": ["product manager"],
    "po": ["product owner"],
    "qa": ["quality assurance", "quality engineer", "test engineer", "đảm bảo chất lượng"],
    "qc": ["quality control", "quality checker", "kiểm soát chất lượng", "kiểm tra chất lượng"],
    "swe": ["software engineer", "software developer"],
    "sse": ["senior software engineer"],
    "tl": ["tech lead", "technical lead"],
    "em": ["engineering manager"],
    "de": ["data engineer"],
    "ds": ["data scientist"],
    "mle": ["machine learning engineer", "ml engineer"],
    "devrel": ["developer relations", "developer advocate"],

    # ── Marketing & Digital (VN ↔ EN) ─────────────────────────────────────────
    "digital marketing": ["tiếp thị số", "tiếp thị kỹ thuật số", "marketing số", "digital mkt"],
    "marketing": ["tiếp thị", "mkt"],
    "content marketing": ["tiếp thị nội dung", "content creator", "sáng tạo nội dung"],
    "seo": ["search engine optimization", "tối ưu công cụ tìm kiếm"],
    "sem": ["search engine marketing"],
    "social media": ["mạng xã hội", "social media marketing", "truyền thông mạng xã hội"],
    "google ads": ["google adwords", "adwords", "quảng cáo google"],
    "facebook ads": ["fb ads", "meta ads", "quảng cáo facebook"],
    "google analytics": ["ga4", "google analytic"],
    "copywriting": ["viết quảng cáo", "content writing", "viết nội dung"],
    "email marketing": ["tiếp thị email", "edm"],
    "branding": ["thương hiệu", "xây dựng thương hiệu", "brand", "brand management"],
    "public relations": ["quan hệ công chúng", "truyền thông báo chí"],
    "market research": ["nghiên cứu thị trường"],
    "kpi": ["key performance indicator", "chỉ số hiệu suất"],
    "crm": ["customer relationship management", "quản lý quan hệ khách hàng"],

    # ── Sales / Business / Customer (VN ↔ EN) ──────────────────────────────────
    "sales": ["bán hàng", "kinh doanh"],
    "b2b": ["business to business"],
    "b2c": ["business to consumer"],
    "customer service": ["chăm sóc khách hàng", "cskh", "dịch vụ khách hàng", "customer support"],
    "telesales": ["bán hàng qua điện thoại", "telemarketing"],
    "account management": ["quản lý khách hàng"],
    "business development": ["phát triển kinh doanh"],

    # ── HR / Admin (VN ↔ EN) ───────────────────────────────────────────────────
    "human resources": ["nhân sự", "quản lý nhân sự", "hr", "quản trị nhân sự"],
    "recruitment": ["tuyển dụng", "talent acquisition"],
    "payroll": ["tính lương", "c&b", "compensation and benefits"],
    "training": ["đào tạo", "l&d", "learning and development"],

    # ── Office / Productivity ─────────────────────────────────────────────────
    "microsoft office": ["ms office", "tin học văn phòng", "microsoft office suite"],
    "excel": ["microsoft excel", "ms excel", "bảng tính"],
    "powerpoint": ["microsoft powerpoint", "ms powerpoint", "power point"],
    "google workspace": ["google suite", "g suite", "google docs", "google sheets"],

    # ── Design / Media tools ──────────────────────────────────────────────────
    "photoshop": ["adobe photoshop"],
    "illustrator": ["adobe illustrator"],
    "premiere pro": ["adobe premiere", "premiere"],
    "after effects": ["adobe after effects"],
    "canva": ["canva design"],
    "capcut": ["cap cut"],
    "graphic design": ["thiết kế đồ họa", "thiết kế đồ hoạ"],
    "video editing": ["chỉnh sửa video", "dựng video", "edit video"],

    # ── Soft skills (VN ↔ EN) ─────────────────────────────────────────────────
    "teamwork": ["làm việc nhóm", "team work", "làm việc theo nhóm", "phối hợp nhóm"],
    "communication": ["giao tiếp", "kỹ năng giao tiếp"],
    "time management": ["quản lý thời gian", "quản trị thời gian"],
    "problem solving": ["giải quyết vấn đề"],
    "leadership": ["lãnh đạo", "kỹ năng lãnh đạo", "khả năng lãnh đạo"],
    "presentation": ["thuyết trình", "kỹ năng thuyết trình"],
    "negotiation": ["đàm phán", "thương lượng"],
    "critical thinking": ["tư duy phản biện", "tư duy phê phán"],
    "adaptability": ["khả năng thích nghi", "thích nghi nhanh"],

    # ── Manufacturing / QA / Ops (esp. garment/production) ─────────────────────
    "lean manufacturing": ["lean", "sản xuất tinh gọn"],
    "kaizen": ["cải tiến liên tục"],
    "5s": ["5s methodology", "quy trình 5s"],
    "production management": ["quản lý sản xuất"],
    "quality management": ["quản lý chất lượng", "qms"],
    "garment": ["may mặc", "dệt may", "hàng may mặc"],
    "supply chain": ["chuỗi cung ứng", "scm"],
    "inventory management": ["quản lý kho", "quản lý hàng tồn kho"],

    # ── Certifications ────────────────────────────────────────────────────────
    "aws certified": [
        "aws certification",
        "solutions architect",
        "cloud practitioner",
        "devops professional",
    ],
    "google certified": [
        "google cloud certification",
        "associate cloud engineer",
        "professional data engineer",
    ],
    "cissp": ["information security certification"],
    "cka": ["certified kubernetes administrator"],
    "ckad": ["certified kubernetes application developer"],
    "pmp": ["project management professional", "pmi"],
    "itil": ["it service management", "itsm"],
    "six sigma": ["lean six sigma", "quality management"],
}


# ---------------------------------------------------------------------------
# 2. One-way implication map (CV → JD direction only)
#    Key: a skill or tool that may appear in a CV.
#    Value: list of prerequisite skills it implies the candidate also knows.
#
#    ONLY add a mapping when the implication is UNAMBIGUOUS:
#      - FastAPI dev → definitely knows Python (framework is built on the lang)
#      - Node.js dev → definitely knows JavaScript (runtime IS JS)
#      - Spring Boot dev → definitely knows Spring and Java
#      - TypeScript dev → definitely knows JavaScript (TS is a strict superset)
#    DO NOT add:
#      - Python → FastAPI (generic lang ≠ specific framework, gap detection)
#      - JavaScript → Node.js (browser JS ≠ server runtime)
#      - Docker → Kubernetes (container skill ≠ orchestration skill)
# ---------------------------------------------------------------------------

_CV_IMPLIES_MAP: dict[str, list[str]] = {
    # Python frameworks → Python
    "fastapi": ["python"],
    "django": ["python"],
    "flask": ["python"],
    "sqlalchemy": ["python"],
    "alembic": ["python"],
    "celery": ["python"],
    "airflow": ["python"],
    "scrapy": ["python"],
    # Java/JVM frameworks → Java
    "spring": ["java"],
    "spring boot": ["java", "spring"],
    "springboot": ["java", "spring"],
    "hibernate": ["java"],
    "jakarta ee": ["java"],
    "junit": ["java"],
    "maven": ["java"],
    "gradle": ["java"],
    # Ruby framework → Ruby
    "rails": ["ruby"],
    # PHP framework → PHP
    "laravel": ["php"],
    "symfony": ["php"],
    # Node.js → JavaScript (Node.js IS a JavaScript runtime)
    "node.js": ["javascript"],
    "nestjs": ["javascript", "node.js", "typescript"],
    "express": ["javascript", "node.js"],
    # TypeScript → JavaScript (strict superset — TS devs know JS syntax/semantics)
    "typescript": ["javascript"],
    # Frontend frameworks → JavaScript
    "react": ["javascript"],
    "vue": ["javascript"],
    "angular": ["javascript"],
    "next.js": ["javascript", "node.js"],
    "nuxt": ["javascript", "vue"],
    "gatsby": ["javascript", "react"],
    "remix": ["javascript", "react"],
    "svelte": ["javascript"],
    "react native": ["javascript", "react"],
    # Go web frameworks → Go
    "gin": ["go"],
    "fiber": ["go"],
    "echo": ["go"],
    # Rust web frameworks → Rust
    "actix": ["rust"],
    "tokio": ["rust"],
    # .NET → C#
    "asp.net": ["c#"],
    "asp.net core": ["c#", ".net"],
    "blazor": ["c#", ".net"],
    "entity framework": ["c#"],
    # Python ML/data libraries → Python
    "pytorch": ["python"],
    "tensorflow": ["python"],
    "keras": ["python"],
    "scikit-learn": ["python"],
    "pandas": ["python"],
    "numpy": ["python"],
    "pyspark": ["python", "apache spark"],
    "hugging face": ["python"],
    "langchain": ["python"],
    "transformers": ["python"],
    # Mobile → base platform language
    "swiftui": ["swift"],
    "flutter": ["dart"],
    "jetpack compose": ["kotlin", "android"],
    "android": ["java"],
    # Scala ecosystem → Scala
    "akka": ["scala"],
    # K8s ecosystem hierarchy
    "helm": ["kubernetes"],
    "argocd": ["kubernetes"],
    "kustomize": ["kubernetes"],
    # DevOps tools → foundational skill
    "terraform": ["infrastructure as code"],
    "ansible": ["linux"],
    # Data pipeline tools
    "dbt": ["sql"],
    "apache spark": ["sql"],
    # Marketing channels/tools → the broader discipline they belong to
    "facebook ads": ["digital marketing"],
    "google ads": ["digital marketing"],
    "seo": ["digital marketing"],
    "email marketing": ["digital marketing"],
    "google analytics": ["digital marketing"],
    # Creative tools → the craft they demonstrate
    "canva": ["graphic design"],
    "photoshop": ["graphic design"],
    "illustrator": ["graphic design"],
    "capcut": ["video editing"],
    "premiere pro": ["video editing"],
    "after effects": ["video editing"],
}


# ---------------------------------------------------------------------------
# Build lookup structures from _EXPANSION_MAP
# ---------------------------------------------------------------------------

# Pre-compiled: token → its full synonym frozenset
_FULL_EXPANSION: dict[str, frozenset[str]] = {}
for _canonical, _aliases in _EXPANSION_MAP.items():
    _all = frozenset({_canonical, *_aliases})
    _FULL_EXPANSION[_canonical] = _all
    for _alias in _aliases:
        _FULL_EXPANSION[_alias] = _all


# ---------------------------------------------------------------------------
# Private helper: word-boundary-aware containment check
# ---------------------------------------------------------------------------

_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}


def _boundary_match(variant: str, text: str) -> bool:
    """Word-boundary-aware containment: ``variant`` must appear as a whole token
    (or whole multi-word phrase), never mid-word.

    Uses a word-boundary regex for ALL variants (not just short ones) so that
    ``"java"`` does not match ``"javascript"``, ``"pm"`` does not match ``"rpm"``,
    and ``"develop"`` does not match ``"developer"``. The boundary class includes
    ``+`` and ``#`` so ``"c"`` does not match ``"c++"``/``"c#"`` and ``"f"`` does
    not match ``"f#"`` (the ``+``/``#`` are treated as part of the adjacent token).
    Prefix-style aliases (e.g. ``"postgres"`` for ``postgresql``) still match
    because synonym expansion injects each alias as a STANDALONE token into the CV
    text, so the boundary regex finds it on its own.
    """
    pattern = _BOUNDARY_CACHE.get(variant)
    if pattern is None:
        pattern = re.compile(r"(?<![a-z0-9+#])" + re.escape(variant) + r"(?![a-z0-9+#])")
        _BOUNDARY_CACHE[variant] = pattern
    return bool(pattern.search(text))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def expand_term(term: str) -> frozenset[str]:
    """Return all known SYNONYM forms of ``term`` (bidirectional, synonym-only).

    Used to expand JD requirement terms before checking against CV text.
    Does NOT include implication expansion so gap detection stays strict.

    Examples::

        expand_term("k8s")       → {"k8s", "kubernetes", "kube"}
        expand_term("pytorch")   → {"pytorch", "torch"}
        expand_term("fastapi")   → {"fastapi", "fast api"}
        expand_term("sql")       → {"sql"}   # unknown → singleton
    """

    normalized = term.lower().strip()
    return _FULL_EXPANSION.get(normalized, frozenset({normalized}))


@lru_cache(maxsize=2048)
def expand_text(text: str) -> str:
    """Enrich a CV text with synonym expansions AND one-way skill implications.

    Pure + deterministic, so results are LRU-cached: the same CV/JD text is
    expanded once and reused. This matters when a page of jobs is scored against a
    user's CVs — each CV's (identical) text would otherwise be re-expanded once per
    job, and synonym expansion over a full CV is the dominant per-score cost.

    Two-phase enrichment:

    Phase 1 — Synonym expansion (bidirectional):
      For each whitespace-separated token found in the text, append all
      synonym aliases so "k8s" in a CV also creates a "kubernetes" signal.

    Phase 2 — Implication expansion (CV → JD one-way):
      For each entry in ``_CV_IMPLIES_MAP``, if the skill appears (substring)
      in the phase-1-expanded text, append all implied skills and their
      synonyms. This makes "node.js" in a CV satisfy a "javascript" JD
      requirement but NOT vice-versa (gap detection is preserved).

    Returns original text (lowercased + normalized) with all expansions
    appended as additional tokens. Never removes original content.
    """

    normalized = re.sub(r"\s+", " ", (text or "").lower())
    added: set[str] = set()
    additions: list[str] = []

    # ── Phase 1: bidirectional synonym expansion ──────────────────────────
    tokens = re.findall(r"[\w#+.\-/]+", normalized)
    for raw in tokens:
        token = raw.strip(".-/")
        if not token:
            continue
        expansion = _FULL_EXPANSION.get(token)
        if not expansion:
            continue
        for t in expansion:
            if t != token and not _boundary_match(t, normalized) and t not in added:
                additions.append(t)
                added.add(t)

    # Build intermediate text (phase 1 results needed for phase 2 checks)
    phase1_text = normalized + (" " + " ".join(additions) if additions else "")

    # ── Phase 2: one-way implication expansion ────────────────────────────
    phase2_additions: list[str] = []
    for skill, implied_skills in _CV_IMPLIES_MAP.items():
        if not implied_skills:
            continue
        # Check if ANY synonym of the skill key is present in phase-1 text.
        skill_forms = _FULL_EXPANSION.get(skill, frozenset({skill}))
        if not any(_boundary_match(f, phase1_text) for f in skill_forms):
            continue
        # Append each implied skill and its synonyms.
        for impl in implied_skills:
            impl_forms = _FULL_EXPANSION.get(impl, frozenset({impl}))
            for t in impl_forms:
                if t not in phase1_text and t not in added:
                    phase2_additions.append(t)
                    added.add(t)

    all_additions = additions + phase2_additions
    if all_additions:
        return normalized + " " + " ".join(all_additions)
    return normalized


def term_matches(term: str, text_normalized: str) -> bool:
    """Return True when ``term`` OR any of its synonyms appears in ``text_normalized``.

    Uses SYNONYM expansion only (not implications) so JD terms are checked
    strictly. The caller must pre-enrich the CV text with ``expand_text()``
    so that CV-side implications are already embedded in ``text_normalized``.

    Examples:
        - CV: "node.js dev" → expand_text appends "javascript js …"
          → term_matches("javascript", expanded_cv) → True ✓
        - CV: "python only" → expand_text appends "py python3 …" (not fastapi!)
          → term_matches("fastapi", expanded_cv) → False → gap ✓
        - CV: "k8s" → expand_text appends "kubernetes kube"
          → term_matches("kubernetes", expanded_cv) → True ✓
    """

    for variant in expand_term(term):
        if _boundary_match(variant, text_normalized):
            return True
    return False
