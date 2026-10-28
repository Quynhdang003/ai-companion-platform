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
