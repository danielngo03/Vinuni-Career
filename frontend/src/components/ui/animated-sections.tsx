"use client";

import { motion, useScroll, useTransform, useInView, useSpring, useMotionValue } from "framer-motion";
import { useEffect, useRef } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Brain,
  Briefcase,
  Buildings,
  CheckCircle,
  ShieldCheck,
  Student,
  ChartLineUp,
  Target,
  Users,
  LockKey
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";

export function AnimatedHero({ vi, locale }: { vi: boolean; locale: string }) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });

  const backgroundY = useTransform(scrollYProgress, [0, 1], ["0%", "50%"]);
  const textY = useTransform(scrollYProgress, [0, 1], ["0%", "30%"]);
  const opacity = useTransform(scrollYProgress, [0, 1], [1, 0]);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        type: "spring" as const,
        stiffness: 100,
        damping: 15,
      },
    },
  };

  return (
    <section ref={ref} className="relative overflow-hidden bg-[#071f43] text-white">
      <motion.div style={{ y: backgroundY }} className="absolute inset-0 z-0 h-[120%] w-full">
        <Image
          src="/images/career-day-2026.jpg"
          alt="VinUniversity Career Day"
          fill
          priority
          className="object-cover object-center opacity-45"
        />
      </motion.div>
      <div className="absolute inset-0 z-10 animate-gradient-shift bg-[linear-gradient(90deg,#071f43_0%,rgba(7,31,67,.94)_42%,rgba(7,31,67,.25)_78%)]" />
      <div className="relative z-20 mx-auto grid min-h-[650px] max-w-7xl items-center px-4 py-20 sm:px-6 lg:grid-cols-[1.05fr_.95fr]">
        <motion.div
          className="max-w-2xl"
          style={{ y: textY, opacity }}
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <motion.div variants={itemVariants} className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-semibold text-cyan-100 backdrop-blur-md">
            <Brain className="size-4" weight="fill" />
            {vi ? "Career intelligence có trách nhiệm" : "Responsible career intelligence"}
          </motion.div>
          <motion.h1 variants={itemVariants} className="text-4xl font-semibold leading-[1.08] tracking-[-0.04em] sm:text-6xl">
            {vi ? "Biến dữ liệu thành cơ hội nghề nghiệp thực tế." : "Turn data into real career opportunities."}
          </motion.h1>
          <motion.p variants={itemVariants} className="mt-6 max-w-xl text-lg leading-8 text-blue-100">
            {vi
              ? "Một nền tảng thống nhất cho sinh viên, doanh nghiệp và nhà trường—từ CV ẩn danh đến tuyển dụng và kiểm duyệt bằng AI."
              : "One platform for students, employers and universities—from privacy-first CVs to AI-assisted recruitment and moderation."}
          </motion.p>
          <motion.div variants={itemVariants} className="mt-9 flex flex-col gap-3 sm:flex-row">
            <Button size="lg" asChild className="bg-white text-navy hover:bg-blue-50 transition-transform hover:scale-105">
              <Link href={`/${locale}/login`}>
                {vi ? "Bắt đầu ngay" : "Get started"}
                <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button
              size="lg"
              variant="outline"
              asChild
              className="border-white/30 bg-white/5 text-white hover:bg-white/10 transition-transform hover:scale-105"
            >
              <a href="#platform">{vi ? "Khám phá nền tảng" : "Explore platform"}</a>
            </Button>
          </motion.div>
          <motion.div variants={itemVariants} className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-blue-100">
            {[
              vi ? "Bảo vệ PII" : "PII protection",
              vi ? "Phân quyền theo tổ chức" : "Organization RBAC",
              vi ? "AI có kiểm soát" : "Governed AI",
            ].map((item) => (
              <motion.span
                key={item}
                className="flex items-center gap-2"
                whileHover={{ scale: 1.05, color: "#fff" }}
              >
                <CheckCircle className="size-4 text-cyan-300" weight="fill" />
                {item}
              </motion.span>
            ))}
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

export function AnimatedMarquee({ vi }: { vi: boolean }) {
  const partners = [
    { name: "VinFast", website: "https://vinfast.com", domain: "vinfast.com" },
    { name: "Vingroup", website: "https://www.vingroup.net", domain: "vingroup.net" },
    { name: "Techcombank", website: "https://techcombank.com", domain: "techcombank.com" },
    { name: "Vinhomes", website: "https://vinhomes.vn", domain: "vinhomes.vn" },
    { name: "Vinmec", website: "https://www.vinmec.com", domain: "vinmec.com" },
    { name: "Vinschool", website: "https://vinschool.edu.vn", domain: "vinschool.edu.vn" },
    { name: "VinAI", website: "https://www.vinai.io", domain: "vinai.io" },
    { name: "VinBigData", website: "https://vinbigdata.com", domain: "vinbigdata.com" },
  ];
  
  return (
    <div className="w-full overflow-hidden bg-white py-10 border-b border-slate-100 flex flex-col items-center">
      <p className="mb-7 text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">
        {vi ? "Được tin dùng bởi các tập đoàn hàng đầu" : "Trusted by leading enterprises"}
      </p>
      <div className="group relative flex w-full max-w-7xl overflow-hidden py-1">
        <div className="pointer-events-none absolute left-0 top-0 z-10 h-full w-32 bg-gradient-to-r from-white to-transparent" />
        <div className="pointer-events-none absolute right-0 top-0 z-10 h-full w-32 bg-gradient-to-l from-white to-transparent" />
        
        <motion.div
          className="flex flex-nowrap items-center gap-5 whitespace-nowrap pr-5"
          animate={{ x: ["0%", "-50%"] }}
          transition={{ ease: "linear", duration: 30, repeat: Infinity }}
        >
          {[...partners, ...partners].map((partner, index) => {
            const isDuplicate = index >= partners.length;

            return (
              <motion.a
                key={`${partner.name}-${index}`}
                href={partner.website}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`${partner.name} — ${vi ? "truy cập trang chủ" : "visit homepage"}`}
                aria-hidden={isDuplicate || undefined}
                tabIndex={isDuplicate ? -1 : undefined}
                whileHover={{ y: -3 }}
                className="focus-ring group/partner flex min-w-[220px] items-center gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm transition-all hover:border-blue-200 hover:shadow-lg"
              >
                <span className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-slate-50 ring-1 ring-slate-100 transition-colors group-hover/partner:bg-blue-50">
                  {/* Google serves the current favicon published by each partner domain. */}
                  <img
                    src={`https://www.google.com/s2/favicons?domain=${partner.domain}&sz=128`}
                    alt=""
                    width={44}
                    height={44}
                    loading="lazy"
                    className="size-11 object-contain"
                  />
                </span>
                <span>
                  <span className="block text-lg font-bold tracking-tight text-slate-800 transition-colors group-hover/partner:text-primary">
                    {partner.name}
                  </span>
                  <span className="mt-1 block text-xs font-medium text-slate-400">
                    {vi ? "Xem trang chủ" : "Visit homepage"} →
                  </span>
                </span>
              </motion.a>
            );
          })}
        </motion.div>
      </div>
    </div>
  );
}

const rolesData = [
  {
    icon: Student,
    titleEn: "Students",
    titleVi: "Sinh viên",
    textEn: "Build CVs, discover matching roles and prepare for interviews.",
    textVi: "Xây CV, tìm cơ hội phù hợp, theo dõi ứng tuyển và chuẩn bị phỏng vấn.",
  },
  {
    icon: Briefcase,
    titleEn: "Employers",
    titleVi: "Doanh nghiệp",
    textEn: "Publish roles, manage candidate pipelines and hire more fairly.",
    textVi: "Đăng tuyển, quản lý pipeline ứng viên và tuyển dụng công bằng hơn.",
  },
  {
    icon: Buildings,
    titleEn: "University",
    titleVi: "Nhà trường",
    textEn: "Moderate, measure and govern the career ecosystem.",
    textVi: "Kiểm duyệt, đo lường hiệu quả và quản trị hệ sinh thái nghề nghiệp.",
  },
];

export function AnimatedRoles({ vi }: { vi: boolean }) {
  const containerRef = useRef(null);
  const isInView = useInView(containerRef, { once: true, margin: "-100px" });

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
      },
    },
  };

  const cardVariants = {
    hidden: { opacity: 0, y: 30 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        type: "spring" as const,
        stiffness: 80,
        damping: 15,
      },
    },
  };

  return (
    <section id="platform" className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
      <div className="max-w-2xl">
        <motion.p
          initial={{ opacity: 0, x: -20 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          className="text-sm font-semibold uppercase tracking-[0.18em] text-primary"
        >
          {vi ? "Một hệ sinh thái" : "One ecosystem"}
        </motion.p>
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="mt-3 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl"
        >
          {vi
            ? "Mỗi vai trò có một workspace riêng, cùng dùng một nguồn dữ liệu."
            : "A focused workspace for every role, powered by one source of truth."}
        </motion.h2>
      </div>
      <motion.div
        ref={containerRef}
        variants={containerVariants}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        id="roles"
        className="mt-10 grid gap-5 md:grid-cols-3"
      >
        {rolesData.map(({ icon: Icon, titleEn, titleVi, textEn, textVi }) => {
          const title = vi ? titleVi : titleEn;
          const text = vi ? textVi : textEn;
          return (
            <motion.article
              key={title}
              variants={cardVariants}
              whileHover={{ 
                y: -8, 
                boxShadow: "0 20px 40px -15px rgba(15, 92, 229, 0.2)",
                borderColor: "rgba(15, 92, 229, 0.3)"
              }}
              className="group rounded-2xl border bg-white p-6 transition-colors duration-300 relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 p-32 bg-blue-50/50 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none -mr-16 -mt-16" />
              <div className="flex size-11 items-center justify-center rounded-xl bg-blue-50 text-primary transition-transform duration-300 group-hover:scale-110 group-hover:bg-blue-100 relative z-10">
                <Icon className="size-6" weight="duotone" />
              </div>
              <h3 className="mt-6 text-xl font-semibold relative z-10">{title}</h3>
              <p className="mt-3 text-sm leading-7 text-muted relative z-10">{text}</p>
            </motion.article>
          );
        })}
      </motion.div>
    </section>
  );
}

export function AnimatedBentoGrid({ vi }: { vi: boolean }) {
  const containerRef = useRef(null);
  
  return (
    <section className="bg-slate-50 py-20 px-4 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl font-semibold sm:text-4xl">
            {vi ? "Vượt xa những chuẩn mực cũ" : "Beyond the standard platform"}
          </h2>
          <p className="mt-4 text-lg text-slate-500 max-w-2xl mx-auto">
            {vi 
              ? "Trải nghiệm được thiết kế lại hoàn toàn với trí tuệ nhân tạo và giao diện đột phá." 
              : "A completely reimagined experience powered by AI and breakthrough interfaces."}
          </p>
        </motion.div>

        <div className="grid gap-6 md:grid-cols-3 md:grid-rows-2 auto-rows-[250px]" ref={containerRef}>
          {/* Card 1 - Large Span */}
          <motion.div 
            className="md:col-span-2 rounded-3xl bg-white border border-slate-200 p-8 relative overflow-hidden group shadow-sm hover:shadow-xl transition-shadow duration-500"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            whileHover={{ y: -4 }}
          >
            <div className="absolute inset-0 bg-gradient-to-br from-blue-50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <Target className="size-8 text-primary mb-4" weight="duotone" />
            <h3 className="text-2xl font-semibold mb-2">{vi ? "Ghép nối AI Thông minh" : "Smart AI Matching"}</h3>
            <p className="text-slate-500 text-lg max-w-md relative z-10">
              {vi 
                ? "Hệ thống hiểu rõ tiềm năng của sinh viên thay vì chỉ lọc từ khóa khô khan."
                : "Our system understands student potential, moving beyond basic keyword filtering."}
            </p>
            <div className="absolute bottom-0 right-0 p-8 translate-y-8 translate-x-8 opacity-10 group-hover:opacity-20 transition-all duration-500">
              <Brain className="size-48" weight="duotone" />
            </div>
          </motion.div>

          {/* Card 2 */}
          <motion.div 
            className="rounded-3xl bg-[#0a192f] text-white p-8 relative overflow-hidden group shadow-sm hover:shadow-xl transition-shadow duration-500"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{ delay: 0.1 }}
            whileHover={{ y: -4 }}
          >
            <LockKey className="size-8 text-cyan-400 mb-4" weight="duotone" />
            <h3 className="text-xl font-semibold mb-2">{vi ? "Bảo mật tuyệt đối" : "Privacy First"}</h3>
            <p className="text-slate-400">
              {vi 
                ? "Hồ sơ ẩn danh giúp loại bỏ định kiến thiên lệch trong tuyển dụng."
                : "Anonymous profiling completely eliminates hiring bias."}
            </p>
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(24,169,196,0.15),transparent_50%)]" />
          </motion.div>

          {/* Card 3 */}
          <motion.div 
            className="rounded-3xl bg-white border border-slate-200 p-8 group hover:border-blue-200 shadow-sm hover:shadow-xl transition-all duration-500"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{ delay: 0.2 }}
            whileHover={{ y: -4 }}
          >
            <Users className="size-8 text-emerald-600 mb-4" weight="duotone" />
            <h3 className="text-xl font-semibold mb-2">{vi ? "Phỏng vấn giả lập" : "Mock Interviews"}</h3>
            <p className="text-slate-500">
              {vi 
                ? "Luyện tập theo thời gian thực cùng phản hồi chi tiết từ AI."
                : "Real-time practice with detailed, actionable AI feedback."}
            </p>
          </motion.div>

          {/* Card 4 - Large Span */}
          <motion.div 
            className="md:col-span-2 rounded-3xl bg-white border border-slate-200 p-8 relative overflow-hidden group shadow-sm hover:shadow-xl transition-shadow duration-500"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{ delay: 0.3 }}
            whileHover={{ y: -4 }}
          >
             <div className="absolute inset-0 bg-gradient-to-tr from-indigo-50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <ChartLineUp className="size-8 text-indigo-600 mb-4" weight="duotone" />
            <h3 className="text-2xl font-semibold mb-2">{vi ? "Phân tích sâu sắc" : "Deep Analytics"}</h3>
            <p className="text-slate-500 text-lg max-w-md relative z-10">
              {vi 
                ? "Cung cấp góc nhìn toàn cảnh về xu hướng việc làm cho Nhà trường và Doanh nghiệp."
                : "Providing comprehensive insights into hiring trends for Universities and Employers."}
            </p>
             <div className="absolute bottom-0 right-0 p-8 translate-y-12 translate-x-8 opacity-5 group-hover:opacity-10 group-hover:-translate-y-2 transition-all duration-700">
              <ChartLineUp className="size-48" weight="fill" />
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function Counter({ value }: { value: number }) {
  const ref = useRef(null);
  const motionValue = useMotionValue(0);
  const springValue = useSpring(motionValue, {
    damping: 60,
    stiffness: 100,
  });
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  useEffect(() => {
    if (isInView) {
      motionValue.set(value);
    }
  }, [motionValue, isInView, value]);

  const display = useTransform(springValue, (current) =>
    Math.round(current).toLocaleString()
  );

  return <motion.span ref={ref}>{display}</motion.span>;
}

export function AnimatedMetrics({ vi }: { vi: boolean }) {
  const metrics = [
    { num: 95, suffix: "%", labelVi: "Độ chính xác ghép nối", labelEn: "Matching Accuracy" },
    { num: 10000, suffix: "+", labelVi: "Cơ hội việc làm", labelEn: "Job Opportunities" },
    { num: 0, suffix: " Bias", labelVi: "Thiên lệch", labelEn: "Hiring Bias" },
  ];

  return (
    <section className="py-24 border-y border-slate-100 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 grid grid-cols-1 md:grid-cols-3 gap-12 divide-y md:divide-y-0 md:divide-x divide-slate-100 text-center">
        {metrics.map((m, i) => (
          <motion.div 
            key={i} 
            className="flex flex-col items-center pt-8 md:pt-0"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1 }}
          >
            <div className="text-5xl md:text-6xl font-bold tracking-tight text-slate-900 mb-2 flex items-center">
              <Counter value={m.num} />
              <span className="text-primary ml-1">{m.suffix}</span>
            </div>
            <p className="text-slate-500 font-medium">{vi ? m.labelVi : m.labelEn}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

export function AnimatedTrust({ vi }: { vi: boolean }) {
  return (
    <section id="trust" className="bg-slate-50 overflow-hidden">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-24 sm:px-6 lg:grid-cols-2 lg:items-center">
        <motion.div
          initial={{ opacity: 0, x: -40 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, type: "spring", bounce: 0.2 }}
        >
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-100 text-primary text-sm font-semibold mb-6">
            <ShieldCheck className="size-4" weight="fill" />
            Trust & Safety
          </div>
          <h2 className="text-4xl font-semibold tracking-[-0.03em]">
            {vi
              ? "AI hỗ trợ quyết định—không thay thế trách nhiệm."
              : "AI supports decisions—it does not replace accountability."}
          </h2>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600">
            {vi
              ? "Dữ liệu nhạy cảm được che trước khi xử lý; mọi gợi ý có bằng chứng, quota và audit trail theo tổ chức. Chúng tôi xây dựng niềm tin từ sự minh bạch."
              : "Sensitive data is masked before processing; recommendations include evidence, quotas and organization-level audit trails. We build trust through transparency."}
          </p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, scale: 0.9, rotate: -2 }}
          whileInView={{ opacity: 1, scale: 1, rotate: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6, type: "spring", bounce: 0.2, delay: 0.2 }}
          whileHover={{ scale: 1.02 }}
          className="relative"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-cyan-400 blur-3xl opacity-20 -z-10" />
          <Image
            src="/images/career-intelligence.png"
            alt="Career intelligence workflow"
            width={1600}
            height={900}
            className="w-full rounded-2xl border border-white/50 bg-white/50 backdrop-blur-sm object-cover shadow-2xl transition-shadow duration-300"
          />
        </motion.div>
      </div>
    </section>
  );
}

export function AnimatedCTA({ vi, locale }: { vi: boolean; locale: string }) {
  return (
    <section className="relative overflow-hidden py-32 bg-[#051124] text-white text-center flex flex-col items-center">
      {/* Animated ambient background */}
      <motion.div 
        animate={{ 
          scale: [1, 1.2, 1],
          opacity: [0.3, 0.5, 0.3],
        }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-primary/40 blur-[120px] rounded-[100%]" 
      />
      
      <div className="relative z-10 px-4 max-w-3xl mx-auto">
        <motion.h2 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-5xl font-semibold tracking-tight mb-8"
        >
          {vi ? "Sẵn sàng định hình tương lai?" : "Ready to shape the future?"}
        </motion.h2>
        <motion.p 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="text-xl text-blue-200 mb-10 max-w-xl mx-auto"
        >
          {vi 
            ? "Gia nhập hệ sinh thái nghề nghiệp hàng đầu ngay hôm nay và mở khóa tiềm năng của bạn."
            : "Join the premier career ecosystem today and unlock your full potential."}
        </motion.p>
        
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2 }}
        >
          <Button size="lg" asChild className="bg-white text-navy hover:bg-slate-100 text-lg px-8 h-14 rounded-full shadow-xl shadow-blue-900/20 transition-transform hover:scale-105">
            <Link href={`/${locale}/login`}>
              {vi ? "Bắt đầu ngay miễn phí" : "Get started for free"}
              <ArrowRight className="size-5 ml-2" />
            </Link>
          </Button>
        </motion.div>
      </div>
    </section>
  );
}
