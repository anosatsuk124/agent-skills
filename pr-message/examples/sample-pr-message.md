# JWTトークンによるユーザー認証機能の追加

## 概要

REST APIにJWTベースの認証を実装し、従来のセッションCookie方式を置き換えました。
ユーザーはサインアップ・ログインを行い、Bearerトークンを使って保護されたエンドポイントに
アクセスできるようになりました。リフレッシュトークンはセキュリティのためHttpOnly Cookieに
保存されます。

## 背景・動機

issue #142 を解決するものです。セッションCookie認証はモバイルアプリおよびステートレスな
認証を必要とするサードパーティAPIクライアントで問題が発生しておりました。Q1計画（RFC-2024-03
参照）においてJWTへの移行が決定されました。

## 主な変更点

- **認証モジュール (`src/auth/`)**: `AuthService`・`JwtStrategy`・`RefreshTokenStrategy` を含む
  新モジュールを追加しました。アクセストークンの有効期限は15分、リフレッシュトークンは7日間です。
- **ユーザー登録 (`src/auth/register.ts`)**: メールアドレスのバリデーション、パスワード強度チェック
  (zxcvbn)、重複メールアドレスに対するわかりやすいエラーメッセージを追加しました。
- **保護ルートガード (`src/middleware/auth-guard.ts`)**: JWTトークンを検証し、デコードされた
  ユーザー情報を `req.user` に付与するExpressミドルウェアを追加しました。トークンが無効または
  期限切れの場合は構造化されたエラーとともに401を返します。
- **DBマイグレーション (`migrations/004_add_refresh_tokens.sql`)**: `user_id` 外部キーと
  有効期限インデックスを持つ `refresh_tokens` テーブルを追加しました。
- **設定更新 (`src/config.ts`)**: `JWT_SECRET` および `JWT_REFRESH_SECRET` を環境変数スキーマに
  バリデーション付きで追加しました。
- **削除**: `src/middleware/session.ts` および `express-session` 依存を削除しました。
  これらは不要になりました。

## テストについて

- [ ] `AuthService` のユニットテスト（トークン生成・検証・リフレッシュフロー）が
  `src/auth/__tests__/auth-service.test.ts` に追加されていることを確認する
- [ ] 認証フロー全体（登録 → ログイン → アクセス → リフレッシュ → ログアウト）の
  インテグレーションテストが `test/integration/auth.test.ts` に追加されていることを確認する
- [ ] `npm run dev` を実行後、`docs/auth-api.postman.json` の Postman コレクションでエンドポイントを手動テストする
- [ ] マイグレーションを実行する: `npm run migrate`

## 破壊的変更

- **すべての認証済みエンドポイントがBearerトークンを必要とするようになりました。**
  クライアントは認証ヘッダーを `Cookie: session=...` から `Authorization: Bearer <token>` に
  変更していただく必要があります。
- **`POST /api/login` のレスポンス形式が変更されました。** Cookieをセットする代わりに
  `{ accessToken, expiresIn }` を返すようになりました。リフレッシュトークンは引き続き
  HttpOnly Cookieに自動でセットされます。
- **`express-session` が削除されました。** `req.session` に依存するコードがある場合、
  デプロイ前に `req.session` の使用箇所を検索してご確認ください。
