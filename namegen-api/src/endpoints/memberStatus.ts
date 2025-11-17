import { Bool, Num, OpenAPIRoute } from "chanfana";
import { z } from "zod";
import { type AppContext } from "../types";

export class MemberStatus extends OpenAPIRoute {
  schema = {
    tags: ["Member"],
    summary: "Member status",
    responses: {
      "200": {
        description: "Membership info",
        content: {
          "application/json": {
            schema: z.object({
              series: z.object({
                success: Bool(),
                result: z.object({
                  is_member: Bool(),
                  monthly_quota: Num(),
                  used_this_month: Num(),
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
      is_member: false,
      monthly_quota: 2,
      used_this_month: 0,
    };
  }
}