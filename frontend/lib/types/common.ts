/** UUID, serialized as a string. */
export type UUID = string;
/** ISO 8601 datetime string (timezone-aware). */
export type DateTimeString = string;
/** ISO 8601 calendar date, `YYYY-MM-DD`. */
export type DateString = string;

export interface OkResponse {
  ok: boolean;
}
