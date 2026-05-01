import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { GraphInput, GraphAnalysisResult } from '../models/sfg.models';

@Injectable({ providedIn: 'root' })
export class SfgService {
  private readonly apiBase = 'http://localhost:8000/api/graph';

  constructor(private http: HttpClient) {}

  analyze(payload: GraphInput): Observable<GraphAnalysisResult> {
    return this.http
      .post<GraphAnalysisResult>(`${this.apiBase}/analyze`, payload)
      .pipe(catchError(this.handleError));
  }

  private handleError(err: HttpErrorResponse): Observable<never> {
    const message =
      err.error?.detail ??
      err.message ??
      'An unexpected error occurred. Is the backend running?';
    return throwError(() => new Error(message));
  }
}
