# Developer Guide

REAL can help protect your applications from bots, spam, and other forms of automated abuse.

SDK installation is fast and easy. You can use HTML/server-side code or native tools.

Plugins and code examples are available for many frameworks.

A complete list of known REAL integrations is also available if you'd like to submit a new one.

## Switching from reCAPTCHA

Existing Google reCAPTCHA code can be used with only a few changes. REAL methods are API-compatible (e.g., render() and onload()). We also support custom data attributes like theme, size, and tab-index.

## Basic Principles

1. You embed the REAL widget on your site. For example, on a login form.
2. The widget challenges the user to prove they are human.
3. Upon completion, REAL provides a response token.
4. You verify the token on your server to ensure it's valid.
5. If valid, you allow the user to proceed with their intended action.

## Request Flow

The typical request flow involves client-side widget rendering, user interaction, token generation, and server-side verification.

## Content-Security-Policy Settings

Configure your CSP headers to allow REAL scripts and resources to load properly while maintaining security.

## Add the REAL Widget to your Webpage

Include the REAL script and add the widget container to your HTML. Configure the widget with your site key and callback functions.

## Verify the User Response Server Side

Send the response token to REAL's verification endpoint to confirm the user's humanity and prevent automated abuse.

## Siteverify Error Codes Table

Reference table for common error codes and their meanings when verifying tokens with REAL's API.

## Rotating Your Siteverify Secret

Best practices for rotating your verification secret to maintain security and prevent token reuse.

## Local Development

Set up your development environment to work with REAL, including test keys and localhost configuration.

## TypeScript Types

TypeScript definitions and interfaces for REAL integration, providing better development experience and type safety.

## How to install

Step-by-step installation guide for different platforms and frameworks.

## How to use

Basic usage examples and common integration patterns for REAL.

## Integration Testing: Test Keys

Use test keys to verify your integration without affecting real users.

## Test Key Set: Publisher or Pro Account

Test keys for publisher and pro account holders.

## Test Key Set: Enterprise Account (Safe End User)

Test keys for enterprise accounts with safe end user scenarios.

## Test Key Set: Enterprise Account (Bot Detected)

Test keys for enterprise accounts with bot detection scenarios.

## Frontend Testing: Force a Visual Challenge

How to force visual challenges during testing to ensure proper widget behavior.

## Backend Testing: Ensure Correct Handling of Rejected Tokens

Test your backend to ensure it properly handles rejected tokens and error scenarios.

## What's next?

Next steps for advanced configuration, customization, and optimization of your REAL integration. 