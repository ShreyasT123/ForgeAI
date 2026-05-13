import readline from 'node:readline/promises';
import {stdin as input, stdout as output} from 'node:process';

import {Command} from '@langchain/langgraph';

import {getSettings} from '../utils/config.js';
import {getLogger} from '../utils/logger.js';
import {safeTokenCompare} from '../utils/security.js';

const logger = getLogger('agents.hitl');

export enum HITLAction {
	APPROVE = 'approve',
	EDIT = 'edit',
	REJECT = 'reject',
}

export class HITLDecision {
	action: HITLAction;
	editedCommand?: string;
	rejectionReason?: string;

	constructor(
		action: HITLAction,
		opts: {editedCommand?: string; rejectionReason?: string} = {},
	) {
		this.action = action;
		this.editedCommand = opts.editedCommand;
		this.rejectionReason = opts.rejectionReason;
	}

	get approved(): boolean {
		return this.action === HITLAction.APPROVE || this.action === HITLAction.EDIT;
	}

	toResumePayload(): Record<string, unknown> {
		const payload: Record<string, unknown> = {approved: this.approved};
		if (this.editedCommand) {
			payload.edited_command = this.editedCommand;
		}
		if (this.rejectionReason) {
			payload.reason = this.rejectionReason;
		}
		return payload;
	}
}

export type HITLPresenter = {
	present(payload: Record<string, unknown>): Promise<HITLDecision> | HITLDecision;
};

export class CLIPresenter implements HITLPresenter {
	async present(payload: Record<string, unknown>): Promise<HITLDecision> {
		const cmd
      = String(payload.command ?? payload.name ?? 'Unknown Action');
		const reason = String(
			payload.reason ?? 'No justification provided.',
		);

		const line = '='.repeat(62);
		const divider = '-'.repeat(62);
		console.log('');
		console.log(line);
		console.log('HUMAN AUTHORIZATION REQUIRED');
		console.log(line);
		console.log(`Action : ${cmd}`);
		console.log(`Reason : ${reason}`);
		console.log(divider);
		console.log('[y] Approve   [e] Edit command   [n] Reject  (default: n)');
		console.log(line);

		const rl = readline.createInterface({input, output});
		try {
			const choice = (await rl.question('  Your choice: ')).trim().toLowerCase();
			if (choice === 'y' || choice === 'yes') {
				logger.info(`HITL approve cmd=${cmd}`);
				return new HITLDecision(HITLAction.APPROVE);
			}
			if (choice === 'e' || choice === 'edit') {
				console.log(`\n  Current: ${cmd}`);
				const edited = (await rl.question('  Modified command (blank = approve as-is): '))
					.trim();
				if (edited) {
					logger.info(`HITL edit cmd=${cmd}`);
					return new HITLDecision(HITLAction.EDIT, {editedCommand: edited});
				}
				logger.info(`HITL approve cmd=${cmd}`);
				return new HITLDecision(HITLAction.APPROVE);
			}
			const rej = (await rl.question('  Rejection reason (optional): ')).trim();
			logger.info(`HITL reject cmd=${cmd}`);
			return new HITLDecision(HITLAction.REJECT, {
				rejectionReason: rej || 'Rejected by human.',
			});
		} catch {
			logger.warn(`HITL prompt interrupted cmd=${cmd}`);
			return new HITLDecision(HITLAction.REJECT, {
				rejectionReason: 'Prompt interrupted.',
			});
		} finally {
			rl.close();
		}
	}
}

export async function handleHitlInterrupt(
	agent: any,
	config: Record<string, unknown>,
	presenter?: HITLPresenter,
): Promise<any | null> {
	const settings = getSettings();

	const state = await agent.getState(config);
	if (!state?.next || state.next.length === 0) {
		return null;
	}
	if (!state.tasks || state.tasks.length === 0) {
		return null;
	}

	const task = state.tasks[0];
	if (!task.interrupts || task.interrupts.length === 0) {
		return null;
	}

	const payload = (task.interrupts[0]?.value ?? {}) as Record<string, unknown>;
	const actionName = String(payload.command ?? payload.name ?? 'Unknown');
	logger.info(`HITL requested action=${actionName}`);
	const configurable = (config as {configurable?: Record<string, unknown>})
		.configurable;
	const provided = configurable?.hitl_bypass_token as string | undefined;
	const expected = settings.hitl_bypass_token ?? undefined;

	if (provided && expected && safeTokenCompare(provided, expected)) {
		logger.info('HITL bypass token accepted');
		const decision = new HITLDecision(HITLAction.APPROVE);
		return await agent.invoke(
			new Command({resume: decision.toResumePayload()}),
			config,
		);
	}

	if (settings.hitl.interactive) {
		const activePresenter = presenter ?? new CLIPresenter();
		const decision = await activePresenter.present(payload);
		logger.info(`HITL decision=${decision.action}`);
		return await agent.invoke(
			new Command({resume: decision.toResumePayload()}),
			config,
		);
	}

	const decision
    = settings.hitl.default_action === 'approve'
    	? new HITLDecision(HITLAction.APPROVE)
    	: new HITLDecision(HITLAction.REJECT, {
    		rejectionReason: 'Non-interactive mode; no bypass token provided.',
    	});

	logger.info(`HITL default decision=${decision.action}`);
	return await agent.invoke(
		new Command({resume: decision.toResumePayload()}),
		config,
	);
}
