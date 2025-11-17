import { Bool, OpenAPIRoute } from "chanfana";
import { z } from "zod";
import { type AppContext } from "../types";

export class MemberActivate extends OpenAPIRoute {
  schema = {
    tags: ["Member"],
    summary: "Activate membership",
    request: {
      body: {
        content: {
          "application/json": {
            schema: z.object({}),
          },
        },
      },
    },
    responses: {
      "200": {
        description: "Activation result",
        content: {
          "application/json": {
            schema: z.object({
              series: z.object({
                success: Bool(),
                result: z.object({
                  activated: Bool(),
                }),
              }),
            }),
          },
        },
      },
    },
  };

  async handle(c: AppContext) {
    return {
      success: true,
      activated: true,
    };
  }
}