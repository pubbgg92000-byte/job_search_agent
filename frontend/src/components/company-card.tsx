import type { CompanySnapshot, NewsItem } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { AlertTriangle, TrendingUp, Briefcase, Newspaper } from "lucide-react";

function ScoreRow({
  label,
  score,
  hint,
}: {
  label: string;
  score: number | null | undefined;
  hint?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="text-sm text-muted-foreground">
        {label}
        {hint && <span className="ml-1 text-[10px]">({hint})</span>}
      </div>
      {score == null ? (
        <Badge variant="outline">unknown</Badge>
      ) : (
        <div className="flex items-center gap-2">
          <div className="w-32 h-1.5 rounded-full bg-muted">
            <div
              className="h-1.5 rounded-full bg-primary"
              style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
            />
          </div>
          <div className="text-xs font-medium w-7 text-right tabular-nums">
            {Math.round(score)}
          </div>
        </div>
      )}
    </div>
  );
}

export function applyLabel(rec: boolean | null | undefined): {
  label: string;
  variant: "success" | "destructive" | "outline";
} | null {
  if (rec === true) return { label: "Apply", variant: "success" };
  if (rec === false) return { label: "Avoid", variant: "destructive" };
  return null;
}

const NEWS_VARIANT: Record<NewsItem["category"], "success" | "destructive" | "secondary" | "outline"> = {
  funding: "success",
  growth: "success",
  layoffs: "destructive",
  news: "outline",
};

function NewsRow({ item }: { item: NewsItem }) {
  return (
    <li className="flex items-start gap-2 py-1.5">
      <Badge variant={NEWS_VARIANT[item.category]} className="text-[10px] capitalize">
        {item.category}
      </Badge>
      <div className="min-w-0">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm hover:text-primary hover:underline truncate block"
          >
            {item.title}
          </a>
        ) : (
          <div className="text-sm">{item.title}</div>
        )}
        {item.summary && (
          <div className="text-xs text-muted-foreground line-clamp-2">{item.summary}</div>
        )}
      </div>
    </li>
  );
}

export function CompanyCard({ company }: { company: CompanySnapshot }) {
  const apply = applyLabel(company.apply_recommendation);
  const techStack = company.tech_stack ?? [];
  const news = company.news_items ?? [];
  const eng = company.engineering_team_signals ?? null;

  return (
    <Card data-testid="company-card">
      <CardHeader>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <CardTitle className="text-lg">{company.name}</CardTitle>
            {company.industry && (
              <div className="text-xs text-muted-foreground mt-0.5">{company.industry}</div>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {company.layoffs_detected && (
              <Badge variant="destructive" className="gap-1">
                <AlertTriangle className="h-3 w-3" />
                Layoffs
              </Badge>
            )}
            {apply && <Badge variant={apply.variant}>{apply.label}</Badge>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3">
          <ScoreRow label="Growth" score={company.growth_score} />
          <ScoreRow label="Risk" score={company.risk_score} />
          <ScoreRow
            label="Hiring"
            score={company.hiring_velocity_score}
            hint={
              company.open_roles_count != null
                ? `${company.open_roles_count} open roles`
                : undefined
            }
          />
          <ScoreRow label="Confidence" score={company.confidence_score} />
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          {company.company_size && (
            <Badge variant="outline">Size: {company.company_size}</Badge>
          )}
          {company.funding_stage && (
            <Badge variant="outline">{company.funding_stage}</Badge>
          )}
          {company.remote_policy && (
            <Badge variant="outline">{company.remote_policy}</Badge>
          )}
          {company.open_roles_count != null && (
            <Badge variant="outline" className="gap-1">
              <Briefcase className="h-3 w-3" />
              {company.open_roles_count} open
            </Badge>
          )}
        </div>

        {techStack.length > 0 && (
          <div>
            <div className="text-xs text-muted-foreground mb-1.5">Tech stack</div>
            <div className="flex flex-wrap gap-1.5">
              {techStack.slice(0, 12).map((t) => (
                <Badge key={t} variant="secondary" className="text-[10px]">
                  {t}
                </Badge>
              ))}
              {techStack.length > 12 && (
                <span className="text-xs text-muted-foreground">+{techStack.length - 12}</span>
              )}
            </div>
          </div>
        )}

        {company.summary && (
          <div>
            <div className="text-xs text-muted-foreground mb-1 inline-flex items-center gap-1">
              <TrendingUp className="h-3 w-3" /> Research summary
            </div>
            <p className="text-sm">{company.summary}</p>
          </div>
        )}

        {eng && Object.keys(eng).length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(eng).map(([k, v]) =>
              v ? (
                <Badge key={k} variant="secondary" className="text-[10px]">
                  {k.replace(/_/g, " ")}
                </Badge>
              ) : null,
            )}
          </div>
        )}

        {news.length > 0 && (
          <div>
            <div className="text-xs text-muted-foreground mb-1 inline-flex items-center gap-1">
              <Newspaper className="h-3 w-3" /> Recent news
            </div>
            <ul className="divide-y divide-border" data-testid="company-news">
              {news.slice(0, 5).map((it, i) => (
                <NewsRow key={`${it.title}-${i}`} item={it} />
              ))}
            </ul>
          </div>
        )}

        {company.website && (
          <a
            href={company.website}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-primary hover:underline"
          >
            {company.website}
          </a>
        )}
      </CardContent>
    </Card>
  );
}
