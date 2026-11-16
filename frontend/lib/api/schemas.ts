import { z } from "zod";

/** Backend error body: `{"error": {"code", "message"}}`. */
export const errorBodySchema = z.object({
  error: z.object({ code: z.string(), message: z.string() }),
});

const timestamp = z.iso.datetime({ offset: true });

export const userRoleSchema = z.enum(["family", "admin"]);
export type UserRole = z.infer<typeof userRoleSchema>;

/** `GET /api/me` */
export const userSchema = z.object({
  id: z.uuid(),
  clerk_user_id: z.string(),
  role: userRoleSchema,
});
export type User = z.infer<typeof userSchema>;

export const elderStatusSchema = z.enum([
  "PENDING_VERIFICATION",
  "ACTIVE",
  "BLOCKED",
]);
export type ElderStatus = z.infer<typeof elderStatusSchema>;

export const familyRoleSchema = z.enum(["owner", "viewer"]);
export type FamilyRole = z.infer<typeof familyRoleSchema>;

/** An elder as seen by a linked family member (`GET /api/elders`). */
export const elderSchema = z.object({
  id: z.uuid(),
  full_name: z.string(),
  preferred_name: z.string().nullable(),
  phone_e164: z.string(),
  status: elderStatusSchema,
  my_role: familyRoleSchema,
  created_at: timestamp,
});
export type Elder = z.infer<typeof elderSchema>;

/** `POST /api/elders` body; `phone` is raw input, normalized by the backend. */
export type ElderCreate = {
  full_name: string;
  phone: string;
  preferred_name: string | null;
};

/** `POST /api/elders`: a taken number returns no data about the existing elder. */
export const registrationSchema = z.discriminatedUnion("result", [
  z.object({ result: z.literal("created"), elder: elderSchema }),
  z.object({ result: z.literal("link_requested"), elder: z.null() }),
]);
export type Registration = z.infer<typeof registrationSchema>;

export const linkRequestStatusSchema = z.enum([
  "pending",
  "approved",
  "rejected",
]);
export type LinkRequestStatus = z.infer<typeof linkRequestStatusSchema>;

/** `GET /api/link-requests/incoming`: pending requests on elders the user owns. */
export const incomingRequestSchema = z.object({
  id: z.uuid(),
  elder: z.object({ id: z.uuid(), full_name: z.string() }),
  // Null until the Clerk webhook has synced the requester.
  requester: z.object({
    display_name: z.string().nullable(),
    email: z.string().nullable(),
  }),
  created_at: timestamp,
});
export type IncomingRequest = z.infer<typeof incomingRequestSchema>;

/** `GET /api/link-requests/outgoing`: the elder's name is only sent once approved. */
export const outgoingRequestSchema = z.object({
  id: z.uuid(),
  phone_e164: z.string(),
  status: linkRequestStatusSchema,
  elder_full_name: z.string().nullable(),
  created_at: timestamp,
  decided_at: timestamp.nullable(),
});
export type OutgoingRequest = z.infer<typeof outgoingRequestSchema>;

/** `POST /api/link-requests/{id}/approve|reject` */
export const linkRequestDecisionSchema = z.object({
  id: z.uuid(),
  status: linkRequestStatusSchema,
  decided_at: timestamp.nullable(),
});

/** `GET /api/telegram`, `DELETE /api/telegram`: `enabled` = Telegram is set up on the server. */
export const telegramStatusSchema = z.object({
  enabled: z.boolean(),
  connected: z.boolean(),
  linked_at: timestamp.nullable(),
});
export type TelegramStatus = z.infer<typeof telegramStatusSchema>;

/** `POST /api/telegram/link`: one-time t.me link to the bot. */
export const telegramLinkSchema = z.object({
  url: z.url(),
  expires_at: timestamp,
});
export type TelegramLink = z.infer<typeof telegramLinkSchema>;

/** `GET /api/elders/{id}`: profile and call activity counts. */
export const elderDetailSchema = elderSchema.extend({
  consent_at: timestamp.nullable(),
  activity: z.object({
    calls_7d: z.number().int(),
    calls_30d: z.number().int(),
    scam_alerts_30d: z.number().int(),
    last_call_at: timestamp.nullable(),
  }),
});
export type ElderDetail = z.infer<typeof elderDetailSchema>;

export const scamTypeSchema = z.enum([
  "police_impersonation",
  "bank_impersonation",
  "relative_impersonation",
  "investment",
  "health_product",
  "resort_contract",
  "fake_charity",
  "other",
]);
export type ScamType = z.infer<typeof scamTypeSchema>;

export const riskLevelSchema = z.enum(["none", "low", "medium", "high"]);
export type RiskLevel = z.infer<typeof riskLevelSchema>;

/** A call's metadata: never anything said in it. */
export const callSchema = z.object({
  id: z.uuid(),
  started_at: timestamp,
  // Null while the call is on, or if its end was never reported.
  duration_seconds: z.number().int().nullable(),
  scam_alerts: z.array(
    z.object({
      scam_type: scamTypeSchema,
      risk_level: riskLevelSchema,
      created_at: timestamp,
    }),
  ),
});
export type Call = z.infer<typeof callSchema>;

/** `GET /api/elders/{id}/calls`: newest first; `next_before` pages on, null on the last. */
export const callPageSchema = z.object({
  calls: z.array(callSchema),
  next_before: timestamp.nullable(),
});
export type CallPage = z.infer<typeof callPageSchema>;

/** Body limits of the admin KB routes (`backend/app/schemas/kb.py`). */
export const KB_TITLE_MAX = 200;
export const KB_CONTENT_MAX = 20_000;
export const KB_SOURCE_MAX = 500;
export const KB_QUERY_MAX = 200;

/** `GET /api/admin/kb/documents`: a document without its text. */
export const kbDocumentSummarySchema = z.object({
  id: z.uuid(),
  title: z.string(),
  // File name or URL it came from, for admins.
  source: z.string().nullable(),
  // How many searchable pieces it was indexed as.
  chunk_count: z.number().int(),
  created_at: timestamp,
  updated_at: timestamp,
});
export type KbDocumentSummary = z.infer<typeof kbDocumentSummarySchema>;

/** `GET|POST|PUT /api/admin/kb/documents[/{id}]` */
export const kbDocumentSchema = kbDocumentSummarySchema.extend({
  content: z.string(),
});
export type KbDocument = z.infer<typeof kbDocumentSchema>;

/** `POST|PUT /api/admin/kb/documents[/{id}]` body. */
export type KbDocumentInput = {
  title: string;
  content: string;
  source: string | null;
};
