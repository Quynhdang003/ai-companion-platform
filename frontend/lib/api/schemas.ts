import { z } from "zod";

/** Backend error body: `{"error": {"code", "message"}}`. */
export const errorBodySchema = z.object({
  error: z.object({ code: z.string(), message: z.string() }),
});

export const userRoleSchema = z.enum(["family", "admin"]);
export type UserRole = z.infer<typeof userRoleSchema>;

/** `GET /api/me` */
export const userSchema = z.object({
  id: z.uuid(),
  clerk_user_id: z.string(),
  role: userRoleSchema,
});
export type User = z.infer<typeof userSchema>;
