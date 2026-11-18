/**
 * HTTP error raised by the shared API client.
 *
 * Kept in its own module so components can branch on the status code (for
 * example a distinct 404 state) without importing the client itself and without
 * depending on a particular test mock of `services/api`.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function isUnprocessable(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422;
}
