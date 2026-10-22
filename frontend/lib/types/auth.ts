export interface LoginRequest {
  username: string;
  password: string;
}

export interface MeResponse {
  authenticated: boolean;
  username: string | null;
}
